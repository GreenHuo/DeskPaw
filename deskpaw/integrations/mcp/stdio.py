"""Small stdio MCP client for the tools hosted by DeskPaw.

The transport speaks the 2025-06-18 JSON-RPC lifecycle. Keeping it separate
from the model loop lets more MCP servers be connected later.
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
from typing import Any


class MCPClient:
    def __init__(self, command: list[str], env: dict[str, str] | None = None) -> None:
        self.command = command
        self.env = env or {}
        self.process: subprocess.Popen[str] | None = None
        self._responses: queue.Queue[dict[str, Any] | Exception] = queue.Queue()
        self._next_id = 0
        self._stderr: list[str] = []

    def __enter__(self) -> MCPClient:
        self.process = subprocess.Popen(
            self.command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
            env={
                **{
                    key: value
                    for key, value in os.environ.items()
                    if key not in {"DEEPSEEK_API_KEY", "DESKPAW_API_KEY"}
                    and not key.startswith("DESKPAW_MCP_TOKEN_")
                },
                **self.env,
            },
        )
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()
        try:
            result = self.request(
                "initialize",
                {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "DeskPaw", "version": "0.1.0"},
                },
                timeout=15,
            )
            if result.get("protocolVersion") not in {
                "2024-11-05",
                "2025-03-26",
                "2025-06-18",
                "2025-11-25",
            }:
                raise RuntimeError("MCP 服务使用了不支持的协议版本")
            self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})
            return self
        except Exception:
            self.close()
            raise

    def __exit__(self, *_: object) -> None:
        self.close()

    def _read_stdout(self) -> None:
        assert self.process is not None and self.process.stdout is not None
        try:
            for line in self.process.stdout:
                if len(line) > 2_000_000:
                    raise RuntimeError("MCP 响应过大")
                self._responses.put(json.loads(line))
        except (OSError, ValueError, RuntimeError) as exc:
            self._responses.put(exc)
        finally:
            self._responses.put(RuntimeError("MCP 服务已退出"))

    def _read_stderr(self) -> None:
        assert self.process is not None and self.process.stderr is not None
        for line in self.process.stderr:
            self._stderr.append(line[-1000:])
            del self._stderr[:-8]

    def _send(self, message: dict[str, Any]) -> None:
        if self.process is None or self.process.stdin is None:
            raise RuntimeError("MCP 服务未启动")
        try:
            self.process.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
            self.process.stdin.flush()
        except OSError as exc:
            raise RuntimeError("无法向 MCP 服务发送请求") from exc

    def request(
        self, method: str, params: dict[str, Any] | None = None, timeout: int = 60
    ) -> dict[str, Any]:
        self._next_id += 1
        request_id = self._next_id
        self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}})
        while True:
            try:
                message = self._responses.get(timeout=timeout)
            except queue.Empty as exc:
                raise RuntimeError(f"MCP 服务响应超时：{method}") from exc
            if isinstance(message, Exception):
                detail = "".join(self._stderr).strip()
                raise RuntimeError(f"{message}{'：' + detail if detail else ''}") from message
            if message.get("id") != request_id:
                if "method" in message and "id" in message:
                    self._send(
                        {
                            "jsonrpc": "2.0",
                            "id": message["id"],
                            "error": {"code": -32601, "message": "Unsupported client method"},
                        }
                    )
                continue
            if "error" in message:
                raise RuntimeError(f"MCP 服务出错：{message['error'].get('message', '未知错误')}")
            result = message.get("result")
            if not isinstance(result, dict):
                raise RuntimeError("MCP 服务返回了无效结果")
            return result

    def list_tools(self) -> list[dict[str, Any]]:
        tools: list[dict[str, Any]] = []
        cursor = None
        for _ in range(16):
            result = self.request("tools/list", {"cursor": cursor} if cursor else {}, timeout=15)
            batch = result.get("tools")
            if not isinstance(batch, list):
                raise RuntimeError("MCP 工具列表无效")
            tools.extend(batch)
            cursor = result.get("nextCursor")
            if not cursor:
                return tools
        raise RuntimeError("MCP 工具列表页数过多")

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return self.request("tools/call", {"name": name, "arguments": arguments})

    def close(self) -> None:
        process, self.process = self.process, None
        if process is None:
            return
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
        for pipe in (process.stdin, process.stdout, process.stderr):
            if pipe is not None:
                pipe.close()
