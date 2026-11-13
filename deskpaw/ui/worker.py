"""Background retrieval, chat requests and tool-approval signals."""

from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from deskpaw.config import (
    Settings,
)
from deskpaw.core.bond import Bond
from deskpaw.knowledge import KnowledgeService
from deskpaw.services.agent import run_excel_agent, run_tool_agent
from deskpaw.services.ai import chat_response


class ChatWorker(QThread):
    answered = Signal(object)
    failed = Signal(str)
    approval_requested = Signal(str)
    progress = Signal(str)

    def __init__(
        self,
        settings: Settings,
        key: str,
        history: list[dict[str, str]],
        bond: Bond | None = None,
        workbook_path: Path | None = None,
        *,
        knowledge: KnowledgeService | None = None,
    ) -> None:
        super().__init__()
        self.settings = settings
        self.knowledge = knowledge if knowledge is not None else KnowledgeService()
        self.key = key
        self.history = history
        self.bond = bond if bond is not None else Bond()
        self.workbook_path = workbook_path
        self._approval_event = threading.Event()
        self._approved = False

    def _await_approval(self, description: str) -> bool:
        self._approval_event.clear()
        self.approval_requested.emit(description)
        if not self._approval_event.wait(300):
            return False
        return self._approved

    def resolve_approval(self, approved: bool) -> None:
        self._approved = approved
        self._approval_event.set()

    def run(self) -> None:
        try:
            query = next(
                (item["content"] for item in reversed(self.history) if item["role"] == "user"), ""
            )
            knowledge_context = self.knowledge.context_for(query)
            has_external_tools = any(server.enabled for server in self.settings.mcp_servers) or any(
                server.enabled for server in self.settings.mcp_http_servers
            )
            is_excel = (
                self.workbook_path is not None and self.workbook_path.suffix.lower() == ".xlsx"
            )
            if self.workbook_path is None and not has_external_tools:
                response = chat_response(
                    self.settings.base_url,
                    self.settings.model,
                    self.key,
                    self.history,
                    self.bond.mood,
                    self.bond.intimacy,
                    self.settings.persona(),
                    knowledge_context=knowledge_context,
                )
            elif is_excel and not has_external_tools:
                response = run_excel_agent(
                    self.settings,
                    self.key,
                    self.history,
                    self.workbook_path,
                    self._await_approval,
                    self.progress.emit,
                    self.bond.mood,
                    self.bond.intimacy,
                    knowledge_context=knowledge_context,
                )
            else:
                response = run_tool_agent(
                    self.settings,
                    self.key,
                    self.history,
                    self.workbook_path,
                    self._await_approval,
                    self.progress.emit,
                    self.bond.mood,
                    self.bond.intimacy,
                    knowledge_context=knowledge_context,
                )
            self.answered.emit(response)
        except Exception as exc:  # Keep network failures in the chat window.
            self.failed.emit(str(exc))
