import os
import threading
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMenu

from deskpaw.config import MCPServerConfig, Settings
from deskpaw.pet.window import PetWindow
from deskpaw.services.ai import ChatResponse
from deskpaw.ui.chat import ChatDialog
from deskpaw.ui.controls import DesktopControls
from deskpaw.ui.mcp_dialogs import MCPServerDialog
from deskpaw.ui.settings import SettingsDialog


class WindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def wait_finished(self, chat):
        deadline = time.monotonic() + 3
        while chat.worker is not None and time.monotonic() < deadline:
            self.app.processEvents()
            QTest.qWait(10)
        self.assertIsNone(chat.worker)

    def test_management_and_pet_menu_share_games_and_dispatch_actions(self):
        pet = PetWindow(Settings(roam=False))
        controls = DesktopControls(pet)
        pet.desktop_controls = controls
        pet.show()
        controls._populate()
        try:
            menu = QMenu()
            pet.populate_menu(menu)
            self.assertEqual(
                [a.text() for a in menu.actions()], [a.text() for a in controls.menu.actions()]
            )
            games = next(a.menu() for a in menu.actions() if a.text() == "小游戏")
            actions = [a for a in games.actions() if not a.isSeparator()][:4]
            self.assertEqual([a.text() for a in actions], ["丢球", "接飞盘", "追光点", "找零食"])
            self.assertTrue(all(not a.icon().isNull() for a in actions))
            for action, mode in zip(actions, ("flying", "flying", "light", "snack_wait")):
                action.trigger()
                self.assertEqual(pet.game_mode, mode)
                pet.stop_game()
            controls.panel.game_buttons[1].click()
            self.assertEqual(pet.toy_kind, "frisbee")
            pet.set_paused(True)
            controls._populate()
            games = next(a.menu() for a in controls.menu.actions() if a.text() == "小游戏")
            self.assertTrue(all(not a.isEnabled() for a in games.actions() if not a.isSeparator()))
            self.assertTrue(all(not b.isEnabled() for b in controls.panel.game_buttons))
        finally:
            pet.shutdown()
            controls.panel.close()
            pet.close()

    def test_chat_keyboard_multiline_and_response_preserve_plain_text_and_actions(self):
        chat = ChatDialog(
            Settings(base_url="http://localhost:8080", pet_name="奶糖", personality="温柔")
        )
        chat.show()
        self.app.processEvents()
        replies = []
        chat.answer_ready.connect(replies.append)
        try:
            chat._use_prompt("握个爪")
            QTest.keyClick(chat.input, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
            self.assertEqual(chat.input.toPlainText(), "握个爪\n")
            chat.input.insertPlainText("<b>原样保留</b>")
            with (
                patch("deskpaw.ui.chat.get_api_key", return_value=""),
                patch(
                    "deskpaw.ui.worker.chat_response",
                    return_value=ChatResponse("给你小爪子！", "handshake", "happy"),
                ) as request,
            ):
                QTest.keyClick(chat.input, Qt.Key.Key_Return)
                self.wait_finished(chat)
            self.assertEqual(
                request.call_args.args[3], [{"role": "user", "content": "握个爪\n<b>原样保留</b>"}]
            )
            self.assertEqual(request.call_args.args[6]["pet_name"], "奶糖")
            self.assertEqual(request.call_args.args[6]["personality"], "温柔")
            self.assertEqual(chat.messages[-2].body.text(), "握个爪\n<b>原样保留</b>")
            self.assertEqual(chat.messages[-2].body.textFormat(), Qt.TextFormat.PlainText)
            self.assertEqual(replies[0].action, "handshake")
            self.assertTrue(chat.send_button.isEnabled())
            self.assertEqual(chat.input.toPlainText(), "")
        finally:
            chat.close()

    def test_selected_excel_uses_agent_worker(self):
        chat = ChatDialog(Settings(base_url="http://localhost:8080"))
        chat.show()
        try:
            with patch(
                "deskpaw.ui.chat.QFileDialog.getOpenFileName", return_value=("/tmp/sales.xlsx", "")
            ):
                chat._choose_excel()
            self.assertEqual(chat.excel_label.text(), "sales.xlsx")
            with (
                patch("deskpaw.ui.chat.get_api_key", return_value=""),
                patch(
                    "deskpaw.ui.worker.run_excel_agent", return_value=ChatResponse("已经看完表格。")
                ) as agent,
            ):
                chat.input.setPlainText("查看工作表")
                chat.send()
                self.wait_finished(chat)
            self.assertEqual(agent.call_args.args[3].name, "sales.xlsx")
            self.assertEqual(chat.messages[-1].body.text(), "已经看完表格。")
            chat._clear_excel()
            self.assertIsNone(chat.workbook_path)
        finally:
            chat.close()

    def test_mcp_service_editor_and_settings_persist(self):
        editor = MCPServerDialog()
        try:
            editor.name.setText("文档工具")
            editor.command.setText("/usr/bin/python3")
            editor.args.setPlainText('["-m", "doc_mcp"]')
            editor._save()
            self.assertEqual(editor.server.args, ["-m", "doc_mcp"])
        finally:
            editor.close()
        with patch("deskpaw.ui.chat.get_api_key", return_value=""):
            dialog = SettingsDialog(Settings(mcp_servers=[editor.server]), initial_tab="mcp")
        try:
            self.assertIn("文档工具", dialog.mcp_list.item(0).text())
            self.assertEqual(dialog.tabs.tabText(dialog.tabs.currentIndex()), "MCP 工具")
            with patch("deskpaw.config.Settings.save"):
                dialog._save()
            self.assertEqual(dialog.settings.mcp_servers[0].command, "/usr/bin/python3")
        finally:
            dialog.close()

    def test_selected_document_routes_to_configured_mcp_agent(self):
        settings = Settings(
            base_url="http://localhost:8080",
            mcp_servers=[MCPServerConfig("文档", "python", ["server.py"])],
        )
        chat = ChatDialog(settings)
        chat.show()
        try:
            with patch(
                "deskpaw.ui.chat.QFileDialog.getOpenFileName", return_value=("/tmp/report.docx", "")
            ):
                chat._choose_excel()
            with (
                patch("deskpaw.ui.chat.get_api_key", return_value=""),
                patch(
                    "deskpaw.ui.worker.run_tool_agent", return_value=ChatResponse("文档处理好了。")
                ) as agent,
            ):
                chat.input.setPlainText("处理这份 Word 文档")
                chat.send()
                self.wait_finished(chat)
            self.assertEqual(agent.call_args.args[3].name, "report.docx")
            self.assertEqual(chat.messages[-1].body.text(), "文档处理好了。")
        finally:
            chat.close()

    def test_persona_settings_save_and_pet_named_you_stays_an_assistant(self):
        with patch("deskpaw.ui.chat.get_api_key", return_value=""):
            dialog = SettingsDialog(Settings())
        try:
            dialog.pet_name.setText("你")
            dialog.owner_name.setText("阿乐")
            dialog.personality.setPlainText("耐心、喜欢讲故事")
            dialog.background.setPlainText("喜欢星星")
            dialog.custom_prompt.setPlainText("用两句话回答。")
            with patch("deskpaw.config.Settings.save"):
                dialog._save()
            self.assertEqual(dialog.settings.custom_prompt, "用两句话回答。")
            self.assertEqual(dialog.settings.owner_name, "阿乐")
            chat = ChatDialog(dialog.settings)
            try:
                chat._answered(ChatResponse("你好，阿乐！"))
                self.assertEqual(chat.messages[-1].role, "assistant")
                self.assertEqual(chat.messages[-1].name.text(), "你")
            finally:
                chat.close()
        finally:
            dialog.close()

    def test_chat_reopens_after_closing_during_background_reply_and_handles_long_messages(self):
        release = threading.Event()
        chat = ChatDialog(Settings(base_url="http://localhost:8080"))
        chat.show()

        def response(*args, **kwargs):
            release.wait(2)
            return ChatResponse("陪着你。" * 150, emotion="neutral")

        try:
            with (
                patch("deskpaw.ui.chat.get_api_key", return_value=""),
                patch("deskpaw.ui.worker.chat_response", side_effect=response),
            ):
                chat.input.setPlainText("陪我一会儿")
                chat.send()
                chat.close()
                self.assertFalse(chat.isVisible())
                release.set()
                self.wait_finished(chat)
            chat.show()
            chat.resize(430, 520)
            self.app.processEvents()
            QTest.qWait(20)
            self.assertTrue(chat.isVisible())
            latest = chat.messages[-1]
            self.assertLessEqual(latest.bubble.width(), chat.transcript.viewport().width() - 50)
            self.assertFalse(chat.transcript.horizontalScrollBar().isVisible())
            self.assertGreater(latest.body.height(), 100)
        finally:
            release.set()
            if chat.worker is not None:
                chat.worker.wait(3000)
                self.app.processEvents()
            chat.close()
