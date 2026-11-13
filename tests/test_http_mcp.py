"""HTTP MCP configuration and agent routing."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from deskpaw.config import MCPHTTPServerConfig, Settings  # noqa: E402
from deskpaw.services.agent import run_tool_agent  # noqa: E402
from deskpaw.ui.settings import SettingsDialog  # noqa: E402


class HTTPMCPConfigTests(unittest.TestCase):
    def test_secure_url_validation_and_settings_roundtrip(self):
        for url in (
            "https://example.com/mcp",
            "http://localhost:8000/mcp",
            "http://127.0.0.1:8000/mcp",
        ):
            MCPHTTPServerConfig("文档", url).validate()
        for url in (
            "http://example.com/mcp",
            "https://user:pass@example.com/mcp",
            "https://example.com/mcp#fragment",
            "https://[bad/mcp",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                MCPHTTPServerConfig("文档", url).validate()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "settings.json"
            settings = Settings(
                mcp_http_servers=[MCPHTTPServerConfig("文档", "https://example.com/mcp")]
            )
            settings.save(path)
            self.assertEqual(Settings.load(path).mcp_http_servers, settings.mcp_http_servers)
            self.assertNotIn("token", path.read_text(encoding="utf-8").lower())

    def test_http_page_saves_token_separately(self):
        app = QApplication.instance() or QApplication([])
        with (
            tempfile.TemporaryDirectory() as folder,
            patch(
                "deskpaw.config.settings.settings_path", return_value=Path(folder) / "settings.json"
            ),
            patch("deskpaw.ui.settings.save_mcp_token") as save_token,
        ):
            dialog = SettingsDialog(Settings(), initial_tab="http_mcp")
            self.assertEqual(dialog.tabs.tabText(dialog.tabs.currentIndex()), "HTTP MCP")
            dialog.http_mcp_servers.append(MCPHTTPServerConfig("文档", "https://example.com/mcp"))
            dialog._pending_http_tokens["https://example.com/mcp"] = "secret-token"
            dialog._save()
            save_token.assert_called_once_with("https://example.com/mcp", "secret-token")
            data = json.loads((Path(folder) / "settings.json").read_text(encoding="utf-8"))
            self.assertEqual(data["mcp_http_servers"][0]["name"], "文档")
            self.assertNotIn("secret-token", json.dumps(data))
            dialog.close()
        app.processEvents()


class HTTPMCPAgentTests(unittest.TestCase):
    def test_http_tool_routes_through_approval(self):
        settings = Settings(
            mcp_http_servers=[MCPHTTPServerConfig("远程文档", "https://example.com/mcp")]
        )
        answer = [
            {
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "mcp_0_0", "arguments": '{"title":"报告"}'},
                    }
                ],
            },
            {"content": "报告已生成。"},
        ]
        approvals = []
        with (
            patch("deskpaw.services.agent.HTTPMCPClient") as client_class,
            patch("deskpaw.services.agent.get_mcp_token", return_value="secret-token"),
            patch("deskpaw.services.agent.completion_message", side_effect=answer),
        ):
            client = client_class.return_value.__enter__.return_value
            client.list_tools.return_value = [
                {"name": "make_pdf", "description": "生成 PDF", "inputSchema": {"type": "object"}}
            ]
            client.call_tool.return_value = {"content": [{"type": "text", "text": "完成"}]}
            response = run_tool_agent(
                settings,
                "model-key",
                [{"role": "user", "content": "生成报告"}],
                None,
                lambda description: approvals.append(description) or True,
            )
        client_class.assert_called_once_with("https://example.com/mcp", "secret-token")
        client.call_tool.assert_called_once_with("make_pdf", {"title": "报告"})
        self.assertIn("远程文档", approvals[0])
        self.assertEqual(response.reply, "报告已生成。")


if __name__ == "__main__":
    unittest.main()
