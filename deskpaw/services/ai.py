"""OpenAI-format chat-completions transport used by DeepSeek and peers."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from deskpaw.knowledge.models import KnowledgeContext

from .prompts import conversation_messages, system_prompt

ACTIONS = {"sleep", "handshake", "happy", "play", "eat", "none"}
EMOTIONS = {"happy", "curious", "sleepy", "excited", "neutral"}


@dataclass(frozen=True)
class ChatResponse:
    reply: str
    action: str = "none"
    emotion: str = "neutral"


def requested_action(message: str) -> str:
    """Honor short, explicit commands even with a text-only compatible model."""
    if re.search(r"(?:不要|不想|别|不准).{0,5}(?:睡|握|爪)", message):
        return "none"
    command = message.strip().strip("。！？!?. ")
    command = re.sub(r"^(?:请|麻烦)?(?:你|柯基|狗狗)?(?:快|现在)?", "", command)
    if command in {"去睡觉", "去睡觉吧", "睡觉", "睡觉吧", "睡一觉", "去睡吧"}:
        return "sleep"
    if command in {"握个爪", "握握爪", "握手", "握手吧", "伸个爪"}:
        return "handshake"
    return "none"


def parse_response(content: str, user_message: str = "") -> ChatResponse:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text).strip()
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        data = None
    if isinstance(data, dict) and isinstance(data.get("reply"), str) and data["reply"].strip():
        reply = data["reply"].strip()
        action = data.get("action") if data.get("action") in ACTIONS else "none"
        emotion = data.get("emotion") if data.get("emotion") in EMOTIONS else "neutral"
    else:
        reply, action, emotion = content.strip(), "none", "neutral"
    explicit = requested_action(user_message)
    if explicit != "none":
        action = explicit
    elif re.search(r"(?:不要|不想|别|不准).{0,5}(?:睡|握|爪)", user_message):
        action = "none"
    if action == "sleep":
        emotion = "sleepy"
    elif action in {"handshake", "play"}:
        emotion = "excited"
    return ChatResponse(reply, action, emotion)


def completion_url(base_url: str) -> str:
    base_url = base_url.strip().rstrip("/")
    parsed = urlparse(base_url)
    if parsed.scheme not in {"https", "http"} or not parsed.netloc:
        raise ValueError("服务地址必须是有效的 HTTP(S) URL")
    if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("远程服务地址必须使用 HTTPS")
    if base_url.endswith("/chat/completions"):
        return base_url
    return base_url + "/chat/completions"


def chat_response(
    base_url: str,
    model: str,
    api_key: str,
    history: list[dict[str, str]],
    mood: int = 50,
    intimacy: int = 0,
    persona: dict[str, str] | None = None,
    *,
    knowledge_context: KnowledgeContext | None = None,
) -> ChatResponse:
    messages = conversation_messages(
        system_prompt(mood, intimacy, persona), history, knowledge_context
    )
    result = completion_message(base_url, model, api_key, messages)
    try:
        content = result["content"]
        if not isinstance(content, str) or not content.strip():
            raise ValueError
        user_message = next(
            (item["content"] for item in reversed(history) if item["role"] == "user"), ""
        )
        return parse_response(content, user_message)
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise RuntimeError("服务返回了无法识别的回复") from exc


def completion_message(
    base_url: str,
    model: str,
    api_key: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Send one OpenAI-format completion and return its assistant message."""
    endpoint = completion_url(base_url)
    local = urlparse(endpoint).hostname in {"localhost", "127.0.0.1", "::1"}
    if not model.strip():
        raise ValueError("请填写模型名称")
    if not api_key.strip() and not local:
        raise ValueError("请先在设置中填写 API Key")
    body: dict[str, Any] = {"model": model.strip(), "messages": messages, "stream": False}
    if tools:
        body["tools"] = tools
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if api_key.strip():
        headers["Authorization"] = f"Bearer {api_key.strip()}"
    request = Request(
        endpoint,
        data=payload,
        headers=headers,
        method="POST",
    )
    try:
        with urlopen(request, timeout=45) as response:
            result = json.load(response)
    except HTTPError as exc:
        detail = exc.read(500).decode("utf-8", errors="replace")
        raise RuntimeError(f"服务返回 HTTP {exc.code}：{detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"网络连接失败：{exc.reason}") from exc
    try:
        message = result["choices"][0]["message"]
        if not isinstance(message, dict):
            raise ValueError
        return message
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise RuntimeError("服务返回了无法识别的回复") from exc


def chat_completion(base_url: str, model: str, api_key: str, history: list[dict[str, str]]) -> str:
    """Text-only compatibility for callers that need just the spoken reply."""
    return chat_response(base_url, model, api_key, history).reply
