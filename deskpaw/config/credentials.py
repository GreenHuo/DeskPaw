"""Service-scoped API and MCP credentials; never stored in settings JSON."""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from urllib.parse import urlparse

from .settings import MCPHTTPServerConfig


def credential_store_name() -> str:
    if sys.platform == "win32":
        return "Windows 凭据管理器"
    if sys.platform == "darwin":
        return "macOS 钥匙串"
    return "环境变量"


def _digest(url: str) -> str:
    return hashlib.sha256(url.strip().lower().encode()).hexdigest()


def _service(base_url: str) -> str:
    return f"com.deskpaw.api.{_digest(base_url)[:16]}"


def _mcp_token_service(url: str) -> str:
    return f"com.deskpaw.mcp.{_digest(url)[:16]}"


def mcp_token_env_name(url: str) -> str:
    return f"DESKPAW_MCP_TOKEN_{_digest(url)[:12].upper()}"


def _keychain(
    action: str, service: str, secret: str | None = None
) -> subprocess.CompletedProcess[str]:
    if action == "find":
        arguments = ["find-generic-password", "-w", "-s", service, "-a", "deskpaw"]
    elif action == "add":
        arguments = [
            "add-generic-password",
            "-U",
            "-s",
            service,
            "-a",
            "deskpaw",
            "-w",
            secret or "",
        ]
    else:
        arguments = ["delete-generic-password", "-s", service, "-a", "deskpaw"]
    return subprocess.run(["security", *arguments], capture_output=True, text=True, check=False)


def _read(service: str, env_name: str) -> str:
    value = os.environ.get(env_name, "").strip()
    if value:
        return value
    if sys.platform == "win32":
        from deskpaw.platform.windows_credentials import WindowsCredentials

        return WindowsCredentials().read(service)
    if sys.platform != "darwin":
        return ""
    result = _keychain("find", service)
    return result.stdout.strip() if result.returncode == 0 else ""


def _write(service: str, secret: str, unsupported_message: str) -> None:
    if sys.platform == "win32":
        from deskpaw.platform.windows_credentials import WindowsCredentials

        WindowsCredentials().write(service, secret)
        return
    if sys.platform != "darwin":
        raise RuntimeError(unsupported_message)
    result = _keychain("add", service, secret)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "无法写入 macOS 钥匙串")


def _delete(service: str, error_message: str) -> bool:
    if sys.platform == "win32":
        from deskpaw.platform.windows_credentials import WindowsCredentials

        return WindowsCredentials().delete(service)
    if sys.platform != "darwin":
        return False
    result = _keychain("delete", service)
    if result.returncode == 0:
        return True
    if "could not be found" in result.stderr.lower():
        return False
    raise RuntimeError(result.stderr.strip() or error_message)


def get_api_key(base_url: str) -> str:
    env_name = (
        "DEEPSEEK_API_KEY"
        if urlparse(base_url).hostname == "api.deepseek.com"
        else "DESKPAW_API_KEY"
    )
    return _read(_service(base_url), env_name)


def save_api_key(base_url: str, key: str) -> None:
    """Save in the OS credential store, never in the settings file."""
    _write(_service(base_url), key, "当前系统请通过 DEEPSEEK_API_KEY 环境变量提供密钥")


def delete_api_key(base_url: str) -> bool:
    """Remove only this service's key; return False if absent."""
    if sys.platform not in {"darwin", "win32"}:
        raise RuntimeError("当前系统没有 macOS 钥匙串密钥")
    return _delete(_service(base_url), "无法删除 macOS 钥匙串密钥")


def get_mcp_token(url: str) -> str:
    return _read(_mcp_token_service(url), mcp_token_env_name(url))


def save_mcp_token(url: str, token: str) -> None:
    MCPHTTPServerConfig("临时服务", url).validate()
    _write(
        _mcp_token_service(url),
        token,
        f"当前系统请通过 {mcp_token_env_name(url)} 环境变量提供 Token",
    )


def delete_mcp_token(url: str) -> bool:
    return _delete(_mcp_token_service(url), "无法删除 MCP Token")
