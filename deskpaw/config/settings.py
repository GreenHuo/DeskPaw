"""Validated non-secret application preferences."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from deskpaw.core.storage import read_json_object, write_json_object

from .paths import settings_path


@dataclass
class MCPServerConfig:
    """One user-enabled local stdio MCP server. Secrets stay in the OS environment."""

    name: str
    command: str
    args: list[str] = field(default_factory=list)
    enabled: bool = True

    def validate(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip() or len(self.name) > 60:
            raise ValueError("MCP 服务名称须为 1 到 60 个字符")
        if not isinstance(self.command, str) or not self.command.strip() or len(self.command) > 500:
            raise ValueError("请填写 MCP 服务的启动命令")
        if not isinstance(self.enabled, bool):
            raise ValueError("MCP 服务启用状态无效")
        if (
            not isinstance(self.args, list)
            or len(self.args) > 40
            or any(not isinstance(arg, str) or len(arg) > 1000 for arg in self.args)
        ):
            raise ValueError("MCP 参数必须是最多 40 项的字符串数组")


@dataclass
class MCPHTTPServerConfig:
    """One remote Streamable HTTP MCP endpoint. Bearer tokens are stored separately."""

    name: str
    url: str
    enabled: bool = True

    def validate(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip() or len(self.name) > 60:
            raise ValueError("HTTP MCP 服务名称须为 1 到 60 个字符")
        if not isinstance(self.url, str) or len(self.url) > 2000:
            raise ValueError("HTTP MCP 地址无效")
        try:
            parsed = urlparse(self.url)
            hostname = parsed.hostname
            _ = parsed.port
        except ValueError as exc:
            raise ValueError("HTTP MCP 地址无效") from exc
        local = hostname in {"localhost", "127.0.0.1", "::1"}
        if not parsed.netloc or parsed.scheme not in ({"http", "https"} if local else {"https"}):
            raise ValueError("远程 MCP 服务须使用 HTTPS；本机服务可使用 HTTP")
        if parsed.username or parsed.password or parsed.fragment:
            raise ValueError("MCP 地址不能包含用户名、密码或片段")
        if not isinstance(self.enabled, bool):
            raise ValueError("HTTP MCP 服务启用状态无效")


def _mcp_http_servers(value: object) -> list[MCPHTTPServerConfig]:
    if not isinstance(value, list):
        return []
    servers = []
    for item in value[:12]:
        if not isinstance(item, dict):
            continue
        server = MCPHTTPServerConfig(
            item.get("name", ""), item.get("url", ""), item.get("enabled", True)
        )
        try:
            server.validate()
        except (TypeError, ValueError):
            continue
        if server.name not in {entry.name for entry in servers} and server.url not in {
            entry.url for entry in servers
        }:
            servers.append(server)
    return servers


def _mcp_servers(value: object) -> list[MCPServerConfig]:
    if not isinstance(value, list):
        return []
    servers = []
    for item in value[:12]:
        if not isinstance(item, dict):
            continue
        server = MCPServerConfig(
            item.get("name", ""),
            item.get("command", ""),
            item.get("args", []),
            item.get("enabled", True),
        )
        try:
            server.validate()
        except (TypeError, ValueError):
            continue
        if server.name not in {entry.name for entry in servers}:
            servers.append(server)
    return servers


@dataclass
class Settings:
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-flash"
    scale: int = 42
    roam: bool = True
    ambient_chatter: bool = True
    effects: bool = True
    idle_seconds: int = 60
    pet_name: str = "柯基"
    owner_name: str = ""
    personality: str = "友好、机灵、温暖，偶尔俏皮，但不会每句都卖萌。"
    background: str = ""
    custom_prompt: str = ""
    mcp_servers: list[MCPServerConfig] = field(default_factory=list)
    mcp_http_servers: list[MCPHTTPServerConfig] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path | None = None) -> Settings:
        path = path or settings_path()
        data = read_json_object(path)
        defaults = cls()
        try:
            scale = max(30, min(120, int(data.get("scale", defaults.scale))))
            idle_seconds = max(15, min(600, int(data.get("idle_seconds", defaults.idle_seconds))))
        except (TypeError, ValueError):
            scale, idle_seconds = defaults.scale, defaults.idle_seconds
        return cls(
            base_url=str(data.get("base_url", defaults.base_url)),
            model=str(data.get("model", defaults.model)),
            scale=scale,
            roam=bool(data.get("roam", defaults.roam)),
            ambient_chatter=bool(data.get("ambient_chatter", defaults.ambient_chatter)),
            effects=bool(data.get("effects", defaults.effects)),
            idle_seconds=idle_seconds,
            pet_name=_text(data.get("pet_name"), defaults.pet_name, 40),
            owner_name=_text(data.get("owner_name"), "", 40),
            personality=_text(data.get("personality"), defaults.personality, 500),
            background=_text(data.get("background"), "", 1500),
            custom_prompt=_text(data.get("custom_prompt"), "", 4000),
            mcp_servers=_mcp_servers(data.get("mcp_servers")),
            mcp_http_servers=_mcp_http_servers(data.get("mcp_http_servers")),
        )

    def persona(self) -> dict[str, str]:
        return {
            name: getattr(self, name)
            for name in ("pet_name", "owner_name", "personality", "background", "custom_prompt")
        }

    def save(self, path: Path | None = None) -> None:
        if len(self.mcp_servers) > 12:
            raise ValueError("最多可配置 12 个 MCP 服务")
        if len(self.mcp_http_servers) > 12:
            raise ValueError("最多可配置 12 个 HTTP MCP 服务")
        names = set()
        for server in self.mcp_servers:
            server.validate()
            if server.name in names:
                raise ValueError(f"MCP 服务名称重复：{server.name}")
            names.add(server.name)
        urls = set()
        for server in self.mcp_http_servers:
            server.validate()
            if server.name in names or server.url in urls:
                raise ValueError(f"HTTP MCP 服务名称或地址重复：{server.name}")
            names.add(server.name)
            urls.add(server.url)
        path = path or settings_path()
        write_json_object(path, asdict(self))


def _text(value: object, default: str, limit: int) -> str:
    return value.strip()[:limit] if isinstance(value, str) and value.strip() else default
