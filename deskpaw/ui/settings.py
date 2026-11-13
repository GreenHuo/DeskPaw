"""Preferences editor and credential-management actions."""

from __future__ import annotations

import os
from urllib.parse import urlparse

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from deskpaw.config import (
    MCPHTTPServerConfig,
    MCPServerConfig,
    Settings,
    credential_store_name,
    delete_api_key,
    delete_mcp_token,
    get_api_key,
    save_api_key,
    save_mcp_token,
)
from deskpaw.ui.theme import STYLE, card, label

from .mcp_dialogs import MCPHTTPServerDialog, MCPServerDialog


class SettingsDialog(QDialog):
    def __init__(
        self, settings: Settings, parent: QWidget | None = None, initial_tab: str = "pet"
    ) -> None:
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("DeskPaw · 设置")
        self.setMinimumWidth(620)
        self.resize(520, 580)
        self.setStyleSheet(STYLE)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(14)
        layout.addWidget(label("让陪伴更合心意", "Title"))
        layout.addWidget(label("调整小狗的习惯，或连接你的聊天服务。"))
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        pet_page = QWidget()
        pet_layout = QVBoxLayout(pet_page)
        pet_layout.setContentsMargins(0, 0, 0, 0)
        pet_layout.setSpacing(14)
        appearance, appearance_layout = card()
        appearance_layout.addWidget(label("外观与活动", "SectionTitle"))
        self.scale = QSlider(Qt.Orientation.Horizontal)
        self.scale.setRange(30, 120)
        self.scale.setValue(settings.scale)
        self.scale_label = label(f"{settings.scale}%", "Badge")
        self.scale.valueChanged.connect(lambda value: self.scale_label.setText(f"{value}%"))
        scale_row = QHBoxLayout()
        scale_row.addWidget(label("宠物大小", "SectionTitle"))
        scale_row.addWidget(self.scale, 1)
        scale_row.addWidget(self.scale_label)
        appearance_layout.addLayout(scale_row)
        self.roam = QCheckBox("允许在桌面散步")
        self.roam.setChecked(settings.roam)
        self.effects = QCheckBox("显示表情和粒子特效")
        self.effects.setChecked(settings.effects)
        appearance_layout.addWidget(self.roam)
        appearance_layout.addWidget(self.effects)
        pet_layout.addWidget(appearance)
        habits, habits_layout = card()
        habits_layout.addWidget(label("陪伴习惯", "SectionTitle"))
        self.ambient = QCheckBox("空闲时主动说话、邀你一起玩")
        self.ambient.setChecked(settings.ambient_chatter)
        habits_layout.addWidget(self.ambient)
        self.idle = QSpinBox()
        self.idle.setRange(15, 600)
        self.idle.setSuffix(" 秒")
        self.idle.setValue(settings.idle_seconds)
        idle_row = QHBoxLayout()
        idle_row.addWidget(label("多久没互动后睡觉", "SectionTitle"), 1)
        idle_row.addWidget(self.idle)
        habits_layout.addLayout(idle_row)
        habits_layout.addWidget(label("心情和亲密度会自动保存，下次见面继续陪你。"))
        pet_layout.addWidget(habits)
        pet_layout.addStretch()
        self.tabs.addTab(pet_page, "宠物偏好")

        persona_page = QScrollArea()
        persona_page.setWidgetResizable(True)
        persona_page.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        persona_body = QWidget()
        persona_layout = QVBoxLayout(persona_body)
        persona_layout.setContentsMargins(0, 0, 8, 0)
        identity, identity_layout = card()
        identity_layout.setContentsMargins(16, 12, 16, 12)
        identity_layout.setSpacing(6)
        identity_layout.addWidget(label("认识你的专属小狗", "SectionTitle"))
        names = QHBoxLayout()
        self.pet_name = QLineEdit(settings.pet_name)
        self.pet_name.setMaxLength(40)
        self.pet_name.setPlaceholderText("给小狗起个名字")
        self.owner_name = QLineEdit(settings.owner_name)
        self.owner_name.setMaxLength(40)
        self.owner_name.setPlaceholderText("小狗怎么称呼你")
        for title, field in (("宠物姓名", self.pet_name), ("你的称呼", self.owner_name)):
            column = QVBoxLayout()
            column.addWidget(label(title))
            column.addWidget(field)
            names.addLayout(column)
        identity_layout.addLayout(names)
        self.personality = QPlainTextEdit(settings.personality)
        self.personality.setFixedHeight(52)
        self.personality.setPlaceholderText("例如：慢热、好奇、嘴硬心软，喜欢鼓励人。")
        self.background = QPlainTextEdit(settings.background)
        self.background.setFixedHeight(52)
        self.background.setPlaceholderText("年龄、爱好、生活背景，或你们之间的小故事。")
        self.custom_prompt = QPlainTextEdit(settings.custom_prompt)
        self.custom_prompt.setFixedHeight(80)
        self.custom_prompt.setPlaceholderText(
            "例如：你叫奶糖，喜欢称呼我阿乐。说话简短、温柔；我疲惫时先陪伴，再给一个小建议。"
        )
        for title, field in (
            ("性格", self.personality),
            ("背景与其他信息", self.background),
            ("自定义提示词", self.custom_prompt),
        ):
            identity_layout.addWidget(label(title))
            identity_layout.addWidget(field)
        identity_layout.addWidget(label("保存后，下一条 AI 回复就会使用这些设定。"))
        persona_layout.addWidget(identity)
        persona_layout.addStretch()
        persona_page.setWidget(persona_body)
        self.tabs.addTab(persona_page, "宠物设定")

        ai_page = QWidget()
        ai_layout = QVBoxLayout(ai_page)
        ai_layout.setContentsMargins(0, 0, 0, 0)
        service, service_layout = card()
        service_layout.addWidget(label("聊天服务", "SectionTitle"))
        self.url = QLineEdit(settings.base_url)
        self.url.setPlaceholderText("https://api.deepseek.com")
        self.model = QLineEdit(settings.model)
        self.model.setPlaceholderText("deepseek-flash")
        service_layout.addWidget(label("服务地址"))
        service_layout.addWidget(self.url)
        service_layout.addWidget(label("模型名称"))
        service_layout.addWidget(self.model)
        service_layout.addWidget(label("API Key"))
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.setPlaceholderText("输入 API Key")
        self.key_visibility = QPushButton("显示")
        self.key_visibility.setCheckable(True)
        self.key_visibility.toggled.connect(self._toggle_key_visibility)
        key_row = QHBoxLayout()
        key_row.addWidget(self.key, 1)
        key_row.addWidget(self.key_visibility)
        service_layout.addLayout(key_row)
        self.key_status = label("")
        self.key_status.setWordWrap(True)
        service_layout.addWidget(self.key_status)
        self.delete_key = QPushButton("删除保存的密钥")
        self.delete_key.setObjectName("Quiet")
        self.delete_key.clicked.connect(self._delete_key)
        service_layout.addWidget(self.delete_key, alignment=Qt.AlignmentFlag.AlignLeft)
        self.key.textChanged.connect(self._update_key_status)
        self.url.editingFinished.connect(self._update_key_status)
        ai_layout.addWidget(service)
        note = label(
            f"密钥保存在{credential_store_name()}，留空可保留已配置的密钥。\n支持兼容 OpenAI 的聊天服务；也可通过环境变量配置密钥。"
        )
        note.setWordWrap(True)
        ai_layout.addWidget(note)
        ai_layout.addStretch()
        ai_index = self.tabs.addTab(ai_page, "AI 聊天")
        mcp_page = QWidget()
        mcp_layout = QVBoxLayout(mcp_page)
        mcp_layout.setContentsMargins(0, 0, 0, 0)
        mcp_layout.setSpacing(12)
        mcp_note = label(
            "添加本地 stdio MCP 服务，宠物会在聊天中发现其工具。每次调用外部工具前会请你确认。"
        )
        mcp_note.setWordWrap(True)
        mcp_layout.addWidget(mcp_note)
        self.mcp_servers = [
            MCPServerConfig(s.name, s.command, list(s.args), s.enabled)
            for s in settings.mcp_servers
        ]
        self.mcp_list = QListWidget()
        self.mcp_list.currentRowChanged.connect(self._update_mcp_buttons)
        mcp_layout.addWidget(self.mcp_list, 1)
        mcp_buttons = QHBoxLayout()
        self.add_mcp_button = QPushButton("添加服务")
        self.add_mcp_button.clicked.connect(self._add_mcp)
        self.edit_mcp_button = QPushButton("编辑")
        self.edit_mcp_button.clicked.connect(self._edit_mcp)
        self.remove_mcp_button = QPushButton("移除")
        self.remove_mcp_button.clicked.connect(self._remove_mcp)
        for button in (self.add_mcp_button, self.edit_mcp_button, self.remove_mcp_button):
            mcp_buttons.addWidget(button)
        mcp_layout.addLayout(mcp_buttons)
        mcp_layout.addWidget(label("支持 PDF、Word 等能力取决于所连接服务提供的工具。"))
        mcp_index = self.tabs.addTab(mcp_page, "MCP 工具")
        self._refresh_mcp_list()
        http_page = QWidget()
        http_layout = QVBoxLayout(http_page)
        http_layout.setContentsMargins(0, 0, 0, 0)
        http_layout.setSpacing(12)
        http_note = label("连接远程 Streamable HTTP MCP 服务。外部工具每次调用前都会请你确认。")
        http_note.setWordWrap(True)
        http_layout.addWidget(http_note)
        self.http_mcp_servers = [
            MCPHTTPServerConfig(s.name, s.url, s.enabled) for s in settings.mcp_http_servers
        ]
        self._pending_http_tokens: dict[str, str] = {}
        self._removed_http_urls: set[str] = set()
        self.http_mcp_list = QListWidget()
        self.http_mcp_list.currentRowChanged.connect(self._update_http_mcp_buttons)
        http_layout.addWidget(self.http_mcp_list, 1)
        http_buttons = QHBoxLayout()
        self.add_http_mcp_button = QPushButton("添加服务")
        self.add_http_mcp_button.clicked.connect(self._add_http_mcp)
        self.edit_http_mcp_button = QPushButton("编辑")
        self.edit_http_mcp_button.clicked.connect(self._edit_http_mcp)
        self.remove_http_mcp_button = QPushButton("移除")
        self.remove_http_mcp_button.clicked.connect(self._remove_http_mcp)
        for button in (
            self.add_http_mcp_button,
            self.edit_http_mcp_button,
            self.remove_http_mcp_button,
        ):
            http_buttons.addWidget(button)
        http_layout.addLayout(http_buttons)
        http_layout.addWidget(label("当前支持无需认证及 Bearer Token 服务；OAuth 登录暂未接入。"))
        http_index = self.tabs.addTab(http_page, "HTTP MCP")
        self._refresh_http_mcp_list()
        if initial_tab == "ai":
            self.tabs.setCurrentIndex(ai_index)
        elif initial_tab == "persona":
            self.tabs.setCurrentIndex(1)
        elif initial_tab == "mcp":
            self.tabs.setCurrentIndex(mcp_index)
        elif initial_tab == "http_mcp":
            self.tabs.setCurrentIndex(http_index)

        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        save = QPushButton("保存设置")
        save.setObjectName("Primary")
        save.clicked.connect(self._save)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        layout.addLayout(buttons)
        self._update_key_status()

    def _refresh_mcp_list(self, selected: int | None = None) -> None:
        self.mcp_list.clear()
        for server in self.mcp_servers:
            state = "已启用" if server.enabled else "已停用"
            self.mcp_list.addItem(f"{server.name} · {state} · {server.command}")
        if self.mcp_servers:
            self.mcp_list.setCurrentRow(
                min(selected if selected is not None else 0, len(self.mcp_servers) - 1)
            )
        self._update_mcp_buttons()

    def _update_mcp_buttons(self, *_: object) -> None:
        selected = self.mcp_list.currentRow() >= 0
        self.edit_mcp_button.setEnabled(selected)
        self.remove_mcp_button.setEnabled(selected)
        self.add_mcp_button.setEnabled(len(self.mcp_servers) < 12)

    def _add_mcp(self) -> None:
        dialog = MCPServerDialog(parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.server is None:
            return
        if dialog.server.name in (
            {server.name for server in self.mcp_servers}
            | {server.name for server in self.http_mcp_servers}
        ):
            QMessageBox.warning(self, "名称重复", "请给 MCP 服务使用不同的名称")
            return
        self.mcp_servers.append(dialog.server)
        self._refresh_mcp_list(len(self.mcp_servers) - 1)

    def _edit_mcp(self) -> None:
        index = self.mcp_list.currentRow()
        if index < 0:
            return
        dialog = MCPServerDialog(self.mcp_servers[index], self)
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.server is None:
            return
        if dialog.server.name in (
            {server.name for i, server in enumerate(self.mcp_servers) if i != index}
            | {server.name for server in self.http_mcp_servers}
        ):
            QMessageBox.warning(self, "名称重复", "请给 MCP 服务使用不同的名称")
            return
        self.mcp_servers[index] = dialog.server
        self._refresh_mcp_list(index)

    def _remove_mcp(self) -> None:
        index = self.mcp_list.currentRow()
        if index >= 0:
            self.mcp_servers.pop(index)
            self._refresh_mcp_list(index)

    def _refresh_http_mcp_list(self, selected: int | None = None) -> None:
        self.http_mcp_list.clear()
        for server in self.http_mcp_servers:
            state = "已启用" if server.enabled else "已停用"
            self.http_mcp_list.addItem(f"{server.name} · {state} · {server.url}")
        if self.http_mcp_servers:
            self.http_mcp_list.setCurrentRow(
                min(selected if selected is not None else 0, len(self.http_mcp_servers) - 1)
            )
        self._update_http_mcp_buttons()

    def _update_http_mcp_buttons(self, *_: object) -> None:
        selected = self.http_mcp_list.currentRow() >= 0
        self.edit_http_mcp_button.setEnabled(selected)
        self.remove_http_mcp_button.setEnabled(selected)
        self.add_http_mcp_button.setEnabled(len(self.http_mcp_servers) < 12)

    def _http_name_taken(self, name: str, skip: int = -1) -> bool:
        return name in {server.name for server in self.mcp_servers} or name in {
            server.name for i, server in enumerate(self.http_mcp_servers) if i != skip
        }

    def _http_url_taken(self, url: str, skip: int = -1) -> bool:
        return url in {server.url for i, server in enumerate(self.http_mcp_servers) if i != skip}

    def _add_http_mcp(self) -> None:
        dialog = MCPHTTPServerDialog(parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.server is None:
            return
        if self._http_name_taken(dialog.server.name) or self._http_url_taken(dialog.server.url):
            QMessageBox.warning(self, "配置重复", "服务名称或地址已存在")
            return
        self.http_mcp_servers.append(dialog.server)
        if dialog.token:
            self._pending_http_tokens[dialog.server.url] = dialog.token
        self._removed_http_urls.discard(dialog.server.url)
        self._refresh_http_mcp_list(len(self.http_mcp_servers) - 1)

    def _edit_http_mcp(self) -> None:
        index = self.http_mcp_list.currentRow()
        if index < 0:
            return
        old_url = self.http_mcp_servers[index].url
        dialog = MCPHTTPServerDialog(self.http_mcp_servers[index], self)
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.server is None:
            return
        if self._http_name_taken(dialog.server.name, index) or self._http_url_taken(
            dialog.server.url, index
        ):
            QMessageBox.warning(self, "配置重复", "服务名称或地址已存在")
            return
        self.http_mcp_servers[index] = dialog.server
        if old_url != dialog.server.url:
            self._removed_http_urls.add(old_url)
            self._pending_http_tokens.pop(old_url, None)
        if dialog.token:
            self._pending_http_tokens[dialog.server.url] = dialog.token
        self._removed_http_urls.discard(dialog.server.url)
        self._refresh_http_mcp_list(index)

    def _remove_http_mcp(self) -> None:
        index = self.http_mcp_list.currentRow()
        if index >= 0:
            server = self.http_mcp_servers.pop(index)
            self._pending_http_tokens.pop(server.url, None)
            self._removed_http_urls.add(server.url)
            self._refresh_http_mcp_list(index)

    def _toggle_key_visibility(self, visible: bool) -> None:
        self.key.setEchoMode(QLineEdit.EchoMode.Normal if visible else QLineEdit.EchoMode.Password)
        self.key_visibility.setText("隐藏" if visible else "显示")

    def _update_key_status(self) -> None:
        if self.key.text():
            self.key_status.setText("新密钥尚未保存")
            return
        base_url = self.url.text().strip().rstrip("/")
        host = urlparse(base_url).hostname
        env_name = "DEEPSEEK_API_KEY" if host == "api.deepseek.com" else "DESKPAW_API_KEY"
        if os.environ.get(env_name, "").strip():
            status = f"已通过环境变量 {env_name} 配置；密钥不会显示"
        else:
            try:
                saved = get_api_key(base_url)
            except RuntimeError:
                self.key_status.setText("系统密钥存储暂不可用，请检查当前用户登录状态。")
                return
            if saved:
                status = f"已保存在{credential_store_name()}；密钥不会显示"
            elif host in {"localhost", "127.0.0.1", "::1"}:
                status = "本地服务可不填 API Key"
            else:
                status = "未配置 API Key"
        self.key_status.setText(status)
        self.key.setPlaceholderText(
            "留空则保持现有密钥" if status.startswith("已") else "输入 API Key"
        )

    def _delete_key(self) -> None:
        try:
            deleted = delete_api_key(self.url.text().strip().rstrip("/"))
        except RuntimeError as exc:
            QMessageBox.warning(self, "无法删除密钥", str(exc))
            return
        self.key.clear()
        self._update_key_status()
        if not deleted:
            self.key_status.setText("系统存储中没有此服务的密钥")
        elif self.key_status.text().startswith("已通过环境变量"):
            self.key_status.setText("保存的密钥已删除；环境变量仍生效")

    def _save(self) -> None:
        from deskpaw.services.ai import completion_url

        try:
            completion_url(self.url.text())
            if not self.model.text().strip():
                raise ValueError("请填写模型名称")
            if not self.pet_name.text().strip():
                raise ValueError("请给宠物填写一个姓名")
            for title, field, limit in (
                ("性格", self.personality, 500),
                ("背景", self.background, 1500),
                ("自定义提示词", self.custom_prompt, 4000),
            ):
                if len(field.toPlainText()) > limit:
                    raise ValueError(f"{title}请控制在 {limit} 字以内")
            new_settings = Settings(
                base_url=self.url.text().strip().rstrip("/"),
                model=self.model.text().strip(),
                scale=self.scale.value(),
                roam=self.roam.isChecked(),
                ambient_chatter=self.ambient.isChecked(),
                effects=self.effects.isChecked(),
                idle_seconds=self.idle.value(),
                pet_name=self.pet_name.text().strip(),
                owner_name=self.owner_name.text().strip(),
                personality=self.personality.toPlainText().strip(),
                background=self.background.toPlainText().strip(),
                custom_prompt=self.custom_prompt.toPlainText().strip(),
                mcp_servers=self.mcp_servers,
                mcp_http_servers=self.http_mcp_servers,
            )
            for server in new_settings.mcp_http_servers:
                server.validate()
            for url, token in self._pending_http_tokens.items():
                save_mcp_token(url, token)
            if self.key.text().strip():
                save_api_key(new_settings.base_url, self.key.text().strip())
            new_settings.save()
            for url in self._removed_http_urls:
                delete_mcp_token(url)
        except (OSError, RuntimeError, ValueError) as exc:
            QMessageBox.warning(self, "无法保存设置", str(exc))
            return
        self.settings = new_settings
        self.accept()
