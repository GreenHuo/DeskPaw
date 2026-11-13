import json
import os
import random
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from deskpaw.config import MCPServerConfig, Settings, delete_api_key, get_api_key
from deskpaw.core.bond import Bond
from deskpaw.services.ai import (
    chat_completion,
    chat_response,
    completion_url,
    parse_response,
)


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self):
        return '{"choices":[{"message":{"content":"汪，你好！"}}]}'.encode()


class CoreTests(unittest.TestCase):
    def test_bond_rewards_persist_and_change_activity_rate(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "bond.json"
            bond = Bond.load(path)
            quiet_delay = Bond(mood=10).ambient_delay(random)
            for _ in range(4):
                bond.reward("feed")
                bond.reward("pet")
                bond.reward("ball")
            saved = Bond.load(path)
            self.assertEqual((saved.mood, saved.intimacy), (100, 36))
            self.assertEqual(saved.level, "cheerful")
            self.assertGreater(quiet_delay, saved.ambient_delay(random))
            path.write_text('{"mood": 999, "intimacy": "bad"}')
            self.assertEqual((Bond.load(path).mood, Bond.load(path).intimacy), (100, 0))

    def test_structured_chat_action_and_plain_text_fallback(self):
        response = parse_response(
            '{"reply":"好呀，晚安！","action":"none","emotion":"happy"}', "去睡觉"
        )
        self.assertEqual((response.action, response.emotion), ("sleep", "sleepy"))
        self.assertEqual(parse_response("汪，来啦！", "握个爪").action, "handshake")
        self.assertEqual(
            parse_response('{"reply":"好","action":"sleep"}', "不要睡觉").action, "none"
        )
        self.assertEqual(parse_response("晚安", "我去睡觉").action, "none")
        self.assertEqual(
            parse_response('{"reply":"好","action":"invalid","emotion":"invalid"}').action, "none"
        )

    def test_structured_chat_response_includes_bond_context(self):
        class JsonResponse(FakeResponse):
            def read(self):
                return (
                    '{"choices":[{"message":{"content":"{\\"reply\\":\\"晚安\\",'
                    '\\"action\\":\\"sleep\\",\\"emotion\\":\\"sleepy\\"}"}}]}'
                ).encode()

        with patch("deskpaw.services.ai.urlopen", return_value=JsonResponse()) as opener:
            response = chat_response(
                "https://api.deepseek.com",
                "deepseek-flash",
                "secret",
                [{"role": "user", "content": "去睡觉"}],
                85,
                40,
            )
        self.assertEqual(
            (response.reply, response.action, response.emotion), ("晚安", "sleep", "sleepy")
        )
        self.assertIn(
            "当前心情 85/100，亲密度 40/100",
            json.loads(opener.call_args.args[0].data)["messages"][0]["content"],
        )

    def test_url_validation(self):
        self.assertEqual(
            completion_url("https://api.deepseek.com"), "https://api.deepseek.com/chat/completions"
        )
        self.assertEqual(
            completion_url("http://localhost:11434/v1"),
            "http://localhost:11434/v1/chat/completions",
        )
        with self.assertRaises(ValueError):
            completion_url("http://example.com")

    def test_chat_request_and_reply(self):
        with patch("deskpaw.services.ai.urlopen", return_value=FakeResponse()) as opener:
            reply = chat_completion(
                "https://api.deepseek.com",
                "deepseek-flash",
                "secret",
                [{"role": "user", "content": "你好"}],
            )
        self.assertEqual(reply, "汪，你好！")
        request = opener.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.deepseek.com/chat/completions")
        body = json.loads(request.data)
        self.assertEqual(body["model"], "deepseek-flash")
        self.assertEqual(body["messages"][-1]["content"], "你好")

    def test_local_service_can_run_without_key(self):
        with patch("deskpaw.services.ai.urlopen", return_value=FakeResponse()) as opener:
            chat_completion(
                "http://localhost:11434/v1", "llama", "", [{"role": "user", "content": "hi"}]
            )
        self.assertNotIn("Authorization", opener.call_args.args[0].headers)

    def test_settings_round_trip_without_secret(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "settings.json"
            Settings(scale=120, idle_seconds=30, ambient_chatter=False, effects=False).save(path)
            self.assertEqual(Settings.load(path).scale, 120)
            self.assertFalse(Settings.load(path).ambient_chatter)
            self.assertFalse(Settings.load(path).effects)
            self.assertNotIn("api_key", path.read_text(encoding="utf-8"))
            path.write_text('{"scale":"bad","idle_seconds":"bad"}')
            self.assertEqual(Settings.load(path).scale, 42)
            self.assertTrue(Settings.load(path).effects)

    def test_mcp_server_settings_round_trip_and_validate(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "settings.json"
            Settings(mcp_servers=[MCPServerConfig("文档工具", "python", ["-m", "doc_mcp"])]).save(
                path
            )
            server = Settings.load(path).mcp_servers[0]
            self.assertEqual(
                (server.name, server.command, server.args, server.enabled),
                ("文档工具", "python", ["-m", "doc_mcp"], True),
            )
            self.assertNotIn("api_key", path.read_text(encoding="utf-8"))
            with self.assertRaises(ValueError):
                Settings(mcp_servers=[MCPServerConfig("坏参数", "python", "-m doc_mcp")]).save(path)

    def test_pet_persona_persists_and_reaches_each_chat_request(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "settings.json"
            settings = Settings(
                pet_name="奶糖",
                owner_name="阿乐",
                personality="慢热但温柔",
                background="喜欢接飞盘，三岁",
                custom_prompt="先倾听，再给一个小建议。",
            )
            settings.save(path)
            restored = Settings.load(path)
            self.assertEqual(restored.persona(), settings.persona())
            with patch("deskpaw.services.ai.urlopen", return_value=FakeResponse()) as opener:
                chat_response(
                    "http://localhost:8080",
                    "test",
                    "",
                    [{"role": "user", "content": "你好"}],
                    70,
                    35,
                    restored.persona(),
                )
            prompt = json.loads(opener.call_args.args[0].data)["messages"][0]["content"]
            for value in restored.persona().values():
                self.assertIn(value, prompt)
            self.assertIn("action", prompt)
            self.assertIn("JSON", prompt)
            self.assertIn("当前心情 70/100", prompt)
            self.assertNotIn("api_key", path.read_text(encoding="utf-8"))

    def test_deepseek_key_not_sent_to_other_host(self):
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "deepseek-only"}, clear=True):
            self.assertEqual(get_api_key("https://api.deepseek.com"), "deepseek-only")
            with patch("deskpaw.config.credentials.sys.platform", "linux"):
                self.assertEqual(get_api_key("https://other.example/v1"), "")

    def test_delete_api_key_removes_only_selected_keychain_item(self):
        class Result:
            returncode = 0
            stderr = ""

        with (
            patch("deskpaw.config.credentials.sys.platform", "darwin"),
            patch("deskpaw.config.credentials.subprocess.run", return_value=Result()) as runner,
        ):
            self.assertTrue(delete_api_key("https://api.deepseek.com"))
        args = runner.call_args.args[0]
        self.assertEqual(args[:2], ["security", "delete-generic-password"])
        self.assertIn("deskpaw", args)
        self.assertNotIn("-w", args)


if __name__ == "__main__":
    unittest.main()
