"""Synchronous adapter for the official MCP Streamable HTTP client."""

from __future__ import annotations

import asyncio
import threading
from concurrent.futures import Future
from concurrent.futures import TimeoutError as FutureTimeout
from contextlib import AsyncExitStack
from typing import Any

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client


class HTTPMCPClient:
    def __init__(self, url: str, token: str = "") -> None:
        self.url = url
        self.token = token
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._client: Client | None = None
        self._ready: Future[None] | None = None
        self._server_task: Future[None] | None = None
        self._stop: asyncio.Event | None = None

    def _run(self, coroutine: Any, timeout: int = 60) -> Any:
        if self._loop is None:
            raise RuntimeError("HTTP MCP 客户端未启动")
        future = asyncio.run_coroutine_threadsafe(coroutine, self._loop)
        try:
            return future.result(timeout=timeout)
        except FutureTimeout as exc:
            future.cancel()
            raise RuntimeError("HTTP MCP 服务响应超时") from exc

    async def _serve(self) -> None:
        assert self._ready is not None
        self._stop = asyncio.Event()
        try:
            async with AsyncExitStack() as stack:
                headers = {"Authorization": f"Bearer {self.token}"} if self.token else None
                http = await stack.enter_async_context(
                    httpx2.AsyncClient(headers=headers, timeout=20)
                )
                self._client = await stack.enter_async_context(
                    Client(
                        streamable_http_client(self.url, http_client=http), read_timeout_seconds=60
                    )
                )
                self._ready.set_result(None)
                await self._stop.wait()
        except BaseException as exc:
            if not self._ready.done():
                self._ready.set_exception(exc)
            else:
                raise
        finally:
            self._client = None

    def __enter__(self) -> HTTPMCPClient:
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()
        self._ready = Future()
        self._server_task = asyncio.run_coroutine_threadsafe(self._serve(), self._loop)
        try:
            self._ready.result(timeout=30)
            return self
        except Exception as exc:
            self.close()
            raise RuntimeError(f"无法连接 HTTP MCP 服务：{exc}") from exc

    def __exit__(self, *_: object) -> None:
        self.close()

    def list_tools(self) -> list[dict[str, Any]]:
        if self._client is None:
            raise RuntimeError("HTTP MCP 客户端未连接")

        async def collect() -> list[dict[str, Any]]:
            assert self._client is not None
            tools: list[dict[str, Any]] = []
            cursor = None
            for _ in range(16):
                result = await self._client.list_tools(cursor=cursor)
                tools.extend(
                    item.model_dump(by_alias=True, exclude_none=True) for item in result.tools
                )
                cursor = result.next_cursor
                if not cursor:
                    return tools
            raise RuntimeError("HTTP MCP 工具列表页数过多")

        return self._run(collect(), timeout=30)

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if self._client is None:
            raise RuntimeError("HTTP MCP 客户端未连接")

        async def call() -> dict[str, Any]:
            assert self._client is not None
            result = await self._client.call_tool(name, arguments)
            return result.model_dump(by_alias=True, exclude_none=True)

        return self._run(call())

    def close(self) -> None:
        try:
            if self._loop is not None and self._stop is not None:
                self._loop.call_soon_threadsafe(self._stop.set)
            if self._server_task is not None:
                self._server_task.result(timeout=10)
        finally:
            self._ready = None
            self._server_task = None
            self._stop = None
            self._client = None
            loop, self._loop = self._loop, None
            thread, self._thread = self._thread, None
            if loop is not None:
                loop.call_soon_threadsafe(loop.stop)
            if thread is not None:
                thread.join(timeout=2)
            if loop is not None and not loop.is_running():
                loop.close()
