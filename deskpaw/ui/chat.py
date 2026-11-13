"""Conversation widgets and chat dialog lifecycle."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from PySide6.QtCore import QEvent, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QFontMetrics, QTextCursor
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from deskpaw.config import (
    Settings,
    get_api_key,
)
from deskpaw.core.bond import Bond
from deskpaw.knowledge import KnowledgeService
from deskpaw.services.ai import ChatResponse
from deskpaw.ui.theme import STYLE, avatar, card, icon, label

from .settings import SettingsDialog
from .worker import ChatWorker


class ChatInput(QPlainTextEdit):
    send_requested = Signal()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if (
            event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
            and not event.modifiers() & Qt.KeyboardModifier.ShiftModifier
        ):
            self.send_requested.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class MessageRow(QWidget):
    def __init__(self, name: str, content: str, role: str, emotion: str = "") -> None:
        super().__init__()
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 5, 0, 5)
        row.setSpacing(10)
        self.bubble, body_layout = card()
        self.bubble.setMaximumWidth(338)
        self.bubble.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        body_layout.setContentsMargins(14, 11, 14, 12)
        body_layout.setSpacing(6)
        heading = QHBoxLayout()
        self.name = label(name, "SectionTitle")
        self.name.setWordWrap(True)
        heading.addWidget(self.name)
        heading.addStretch()
        if emotion:
            badge = QFrame()
            badge.setObjectName("EmotionBadge")
            badge_row = QHBoxLayout(badge)
            badge_row.setContentsMargins(7, 3, 7, 3)
            badge_row.setSpacing(4)
            face = QLabel()
            expression = {
                "开心": "happy",
                "好奇": "curious",
                "困困": "sleepy",
                "兴奋": "excited",
            }.get(emotion, "neutral")
            face.setPixmap(icon(expression).pixmap(QSize(14, 14)))
            badge_row.addWidget(face)
            badge_row.addWidget(label(emotion))
            heading.addWidget(badge)
        body_layout.addLayout(heading)
        self.body = QLabel(content)
        self.body.setTextFormat(Qt.TextFormat.PlainText)
        self.body.setWordWrap(True)
        self.body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.body.setMinimumWidth(0)
        body_layout.addWidget(self.body)
        self.role = role
        if role == "user":
            self.bubble.setStyleSheet("QFrame#Card { background: #f4e3d0; border-color: #eed8bf; }")
            row.addStretch()
            row.addWidget(self.bubble)
        else:
            portrait = QLabel()
            portrait.setPixmap(avatar(30))
            row.addWidget(portrait, 0, Qt.AlignmentFlag.AlignTop)
            if role == "error":
                self.bubble.setStyleSheet(
                    "QFrame#Card { background: #fff0ec; border-color: #efcec3; }"
                )
            row.addWidget(self.bubble)
            row.addStretch()

    def fit_width(self, available: int) -> None:
        self.body.ensurePolished()
        metrics = QFontMetrics(self.body.font())
        content_width = max(
            (metrics.horizontalAdvance(line) for line in self.body.text().splitlines()), default=0
        )
        self.bubble.setFixedWidth(
            min(
                338,
                max(100, available),
                max(140 if self.role != "user" else 100, content_width + 30),
            )
        )


class ChatDialog(QDialog):
    settings_changed = Signal(object)
    answer_ready = Signal(object)

    def __init__(
        self,
        settings: Settings,
        parent: QWidget | None = None,
        bond: Bond | None = None,
        *,
        knowledge: KnowledgeService | None = None,
    ) -> None:
        super().__init__(parent)
        self.settings = settings
        self.knowledge = knowledge
        self.bond = bond if bond is not None else Bond()
        self.session_key = ""
        self.history: list[dict[str, str]] = []
        self.workbook_path: Path | None = None
        self.worker: ChatWorker | None = None
        self.messages: list[MessageRow] = []
        self.setWindowTitle(f"DeskPaw · 和{settings.pet_name}聊聊")
        self.setMinimumSize(430, 520)
        self.resize(480, 620)
        self.setStyleSheet(STYLE)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 16)
        layout.setSpacing(14)
        header = QHBoxLayout()
        portrait = QLabel()
        portrait.setPixmap(avatar(46))
        header.addWidget(portrait)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        self.title_label = label(f"和{settings.pet_name}聊聊", "Title")
        self.title_label.setWordWrap(True)
        titles.addWidget(self.title_label)
        titles.addWidget(label("听你说话，也陪你做点小事"))
        header.addLayout(titles, 1)
        self.settings_button = QPushButton(icon("settings"), "设置")
        self.settings_button.setObjectName("Quiet")
        self.settings_button.clicked.connect(self.open_settings)
        header.addWidget(self.settings_button)
        layout.addLayout(header)
        self.bond_label = label("", "Badge")
        layout.addWidget(self.bond_label, alignment=Qt.AlignmentFlag.AlignLeft)
        self._refresh_bond()

        self.transcript = QScrollArea()
        self.transcript.setWidgetResizable(True)
        self.transcript.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.transcript.viewport().installEventFilter(self)
        conversation = QWidget()
        self.conversation_layout = QVBoxLayout(conversation)
        self.conversation_layout.setContentsMargins(0, 2, 8, 4)
        self.conversation_layout.setSpacing(4)
        self.conversation_layout.addStretch()
        self.transcript.setWidget(conversation)
        layout.addWidget(self.transcript, 1)
        self._append(
            settings.pet_name, f"嗨，我是{settings.pet_name}。今天想聊什么？", "", role="assistant"
        )
        attachment = QHBoxLayout()
        self.excel_button = QPushButton("选择文件")
        self.excel_button.setObjectName("Quiet")
        self.excel_button.clicked.connect(self._choose_excel)
        attachment.addWidget(self.excel_button)
        self.excel_label = label("未选择文件")
        self.excel_label.setWordWrap(True)
        attachment.addWidget(self.excel_label, 1)
        self.clear_excel_button = QPushButton("移除")
        self.clear_excel_button.setObjectName("Quiet")
        self.clear_excel_button.setEnabled(False)
        self.clear_excel_button.clicked.connect(self._clear_excel)
        attachment.addWidget(self.clear_excel_button)
        layout.addLayout(attachment)
        chips = QHBoxLayout()
        for prompt in ("握个爪", "去睡觉", "夸夸我"):
            chip = QPushButton(prompt)
            chip.setObjectName("Chip")
            chip.clicked.connect(lambda checked=False, text=prompt: self._use_prompt(text))
            chips.addWidget(chip)
        chips.addStretch()
        layout.addLayout(chips)
        composer = QHBoxLayout()
        self.input = ChatInput()
        self.input.setFixedHeight(70)
        self.input.setPlaceholderText("说点什么吧…")
        self.input.send_requested.connect(self.send)
        self.send_button = QPushButton(icon("send", "#ffffff"), "发送")
        self.send_button.setObjectName("Primary")
        self.send_button.setMinimumHeight(44)
        self.send_button.clicked.connect(self.send)
        composer.addWidget(self.input, 1)
        composer.addWidget(self.send_button)
        layout.addLayout(composer)
        footer = QHBoxLayout()
        self.status = label("准备好听你说话")
        footer.addWidget(self.status, 1)
        footer.addWidget(label("Enter 发送 · Shift+Enter 换行"))
        layout.addLayout(footer)

    def _refresh_bond(self) -> None:
        mood = {"quiet": "低落", "normal": "平静", "cheerful": "开心"}[self.bond.level]
        self.bond_label.setText(f"心情 {mood} · 亲密度 {self.bond.intimacy}")

    def _use_prompt(self, text: str) -> None:
        self.input.setPlainText(text)
        self.input.moveCursor(QTextCursor.MoveOperation.End)
        self.input.setFocus()

    def _choose_excel(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "选择任务文件",
            "",
            "文档 (*.xlsx *.docx *.pdf);;所有文件 (*)",
        )
        if filename:
            self.workbook_path = Path(filename)
            self.excel_label.setText(self.workbook_path.name)
            self.clear_excel_button.setEnabled(True)
            if self.workbook_path.suffix.lower() != ".xlsx" and not (
                any(server.enabled for server in self.settings.mcp_servers)
                or any(server.enabled for server in self.settings.mcp_http_servers)
            ):
                self.status.setText("已选择文件；请先在设置中添加文档 MCP 服务")
            else:
                self.status.setText("已选择文件；文件路径与工具读取的内容会发送给聊天模型")

    def _clear_excel(self) -> None:
        self.workbook_path = None
        self.excel_label.setText("未选择文件")
        self.clear_excel_button.setEnabled(False)
        self.status.setText("准备好听你说话")

    def open_settings(self) -> None:
        dialog = SettingsDialog(self.settings, self, initial_tab="ai")
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.settings = dialog.settings
            self.session_key = ""
            self.settings_changed.emit(self.settings)
            self._refresh_identity()
            self.status.setText("聊天设置已更新")

    def _refresh_identity(self) -> None:
        self.title_label.setText(f"和{self.settings.pet_name}聊聊")
        self.setWindowTitle(f"DeskPaw · 和{self.settings.pet_name}聊聊")

    def send(self) -> None:
        message = self.input.toPlainText().strip()
        if not message or self.worker is not None:
            return
        try:
            key = self.session_key or get_api_key(self.settings.base_url)
        except RuntimeError as exc:
            self.status.setText(str(exc))
            return
        local = urlparse(self.settings.base_url).hostname in {"localhost", "127.0.0.1", "::1"}
        if not key and not local:
            self.open_settings()
            try:
                key = get_api_key(self.settings.base_url)
            except RuntimeError as exc:
                self.status.setText(str(exc))
                return
            if not key:
                self.status.setText("先在设置里连接聊天服务")
                return
        self.input.clear()
        self._append("你", message, "", role="user")
        self.history.append({"role": "user", "content": message})
        self.status.setText(f"{self.settings.pet_name}正在想怎么回答…")
        self.send_button.setEnabled(False)
        self.excel_button.setEnabled(False)
        self.clear_excel_button.setEnabled(False)
        self.worker = ChatWorker(
            self.settings,
            key,
            list(self.history),
            self.bond,
            self.workbook_path,
            knowledge=self.knowledge,
        )
        self.worker.answered.connect(self._answered)
        self.worker.failed.connect(self._failed)
        self.worker.approval_requested.connect(self._approve_excel_write)
        self.worker.progress.connect(self.status.setText)
        self.worker.finished.connect(self._finished)
        self.worker.start()

    def _approve_excel_write(self, description: str) -> None:
        decision = QMessageBox.question(
            self,
            "允许调用工具？",
            description,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if self.worker is not None:
            self.worker.resolve_approval(decision == QMessageBox.StandardButton.Yes)

    def _append(
        self, name: str, content: str, color: str, emotion: str = "", role: str | None = None
    ) -> None:
        role = role or ("user" if name == "你" else "error" if name == "连接失败" else "assistant")
        message = MessageRow(name, content, role, emotion)
        self.messages.append(message)
        self.conversation_layout.insertWidget(self.conversation_layout.count() - 1, message)
        message.fit_width(self.transcript.viewport().width() - 50)
        QTimer.singleShot(0, self._scroll_to_latest)

    def _scroll_to_latest(self) -> None:
        bar = self.transcript.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _answered(self, response: ChatResponse) -> None:
        self.history.append({"role": "assistant", "content": response.reply})
        expression = {
            "happy": "开心",
            "curious": "好奇",
            "sleepy": "困困",
            "excited": "兴奋",
            "neutral": "陪着你",
        }[response.emotion]
        self._append(self.settings.pet_name, response.reply, "", expression, role="assistant")
        self.answer_ready.emit(response)
        self._refresh_bond()
        self.status.setText("准备好听你说话")

    def _failed(self, error: str) -> None:
        if self.history and self.history[-1]["role"] == "user":
            self.history.pop()
        self._append("连接失败", error, "")
        self.status.setText("连接有点问题，可以检查设置后再试")

    def _finished(self) -> None:
        self.send_button.setEnabled(True)
        self.excel_button.setEnabled(True)
        self.clear_excel_button.setEnabled(self.workbook_path is not None)
        if self.worker is not None:
            self.worker.deleteLater()
        self.worker = None
        self.input.setFocus()

    def showEvent(self, event) -> None:  # noqa: N802
        self._refresh_bond()
        self._refresh_identity()
        super().showEvent(event)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if hasattr(self, "transcript"):
            QTimer.singleShot(0, self._fit_messages)

    def _fit_messages(self) -> None:
        for message in self.messages:
            message.fit_width(self.transcript.viewport().width() - 50)

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        if (
            hasattr(self, "transcript")
            and watched == self.transcript.viewport()
            and event.type() == QEvent.Type.Resize
        ):
            QTimer.singleShot(0, self._fit_messages)
        return super().eventFilter(watched, event)

    def closeEvent(self, event) -> None:  # noqa: N802
        if self.worker is not None:
            self.hide()
            event.ignore()
            return
        super().closeEvent(event)
