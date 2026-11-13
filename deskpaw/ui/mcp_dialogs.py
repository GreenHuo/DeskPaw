"""Editors for stdio and HTTP MCP service connections."""

from __future__ import annotations

import json

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from deskpaw.config import (
    MCPHTTPServerConfig,
    MCPServerConfig,
    credential_store_name,
)
from deskpaw.ui.theme import STYLE, label


class MCPServerDialog(QDialog):
    def __init__(
        self, server: MCPServerConfig | None = None, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.server: MCPServerConfig | None = None
        self.setWindowTitle("MCP 服务")
        self.setMinimumWidth(460)
        self.setStyleSheet(STYLE)
        layout = QVBoxLayout(self)
        layout.addWidget(label("服务名称"))
        self.name = QLineEdit(server.name if server else "")
        self.name.setPlaceholderText("例如：文档工具")
        layout.addWidget(self.name)
        layout.addWidget(label("启动命令"))
        self.command = QLineEdit(server.command if server else "")
        self.command.setPlaceholderText("例如：python 或绝对路径；不会经过 shell")
        layout.addWidget(self.command)
        layout.addWidget(label("参数（JSON 字符串数组）"))
        self.args = QPlainTextEdit(json.dumps(server.args if server else [], ensure_ascii=False))
        self.args.setFixedHeight(72)
        self.args.setPlaceholderText('["-m", "my_document_mcp"]')
        layout.addWidget(self.args)
        self.enabled = QCheckBox("启用此服务")
        self.enabled.setChecked(server.enabled if server else True)
        layout.addWidget(self.enabled)
        note = label("服务以当前用户权限运行。密钥请通过系统环境变量提供，不要写进参数。")
        note.setWordWrap(True)
        layout.addWidget(note)
        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        save = QPushButton("确定")
        save.setObjectName("Primary")
        save.clicked.connect(self._save)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        layout.addLayout(buttons)

    def _save(self) -> None:
        try:
            args = json.loads(self.args.toPlainText())
            server = MCPServerConfig(
                self.name.text().strip(),
                self.command.text().strip(),
                args,
                self.enabled.isChecked(),
            )
            server.validate()
        except (TypeError, ValueError) as exc:
            QMessageBox.warning(self, "无法保存 MCP 服务", str(exc))
            return
        self.server = server
        self.accept()


class MCPHTTPServerDialog(QDialog):
    def __init__(
        self, server: MCPHTTPServerConfig | None = None, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.server: MCPHTTPServerConfig | None = None
        self.token = ""
        self.setWindowTitle("HTTP MCP 服务")
        self.setMinimumWidth(460)
        self.setStyleSheet(STYLE)
        layout = QVBoxLayout(self)
        layout.addWidget(label("服务名称"))
        self.name = QLineEdit(server.name if server else "")
        self.name.setPlaceholderText("例如：远程文档工具")
        layout.addWidget(self.name)
        layout.addWidget(label("Streamable HTTP 地址"))
        self.url = QLineEdit(server.url if server else "")
        self.url.setPlaceholderText("https://example.com/mcp")
        layout.addWidget(self.url)
        layout.addWidget(label("Bearer Token（可选）"))
        self.token_input = QLineEdit()
        self.token_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.token_input.setPlaceholderText("留空则使用已保存的 Token")
        layout.addWidget(self.token_input)
        self.enabled = QCheckBox("启用此服务")
        self.enabled.setChecked(server.enabled if server else True)
        layout.addWidget(self.enabled)
        note = label(
            f"远程地址须使用 HTTPS，本机地址可用 HTTP。Token 保存在{credential_store_name()}，不会写入设置文件。"
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        save = QPushButton("确定")
        save.setObjectName("Primary")
        save.clicked.connect(self._save)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        layout.addLayout(buttons)

    def _save(self) -> None:
        try:
            server = MCPHTTPServerConfig(
                self.name.text().strip(), self.url.text().strip(), self.enabled.isChecked()
            )
            server.validate()
        except ValueError as exc:
            QMessageBox.warning(self, "无法保存 HTTP MCP 服务", str(exc))
            return
        self.server = server
        self.token = self.token_input.text().strip()
        self.accept()
