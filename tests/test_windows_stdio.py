"""Exercise UTF-8 MCP pipes with and without a Windows console."""

import io
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from deskpaw.platform.windows_stdio import configure_mcp_stdio


class WindowsStdioTests(unittest.TestCase):
    def test_existing_redirected_streams_use_utf8_for_chinese_protocol_messages(self):
        incoming = io.BytesIO('{"text":"你好🐾"}\n'.encode())
        outgoing, errors = io.BytesIO(), io.BytesIO()
        streams = {
            "stdin": io.TextIOWrapper(incoming, encoding="cp1252"),
            "stdout": io.TextIOWrapper(outgoing, encoding="cp1252"),
            "stderr": io.TextIOWrapper(errors, encoding="cp1252"),
        }
        with patch("sys.platform", "win32"), patch.multiple(sys, **streams):
            configure_mcp_stdio()
            message = json.loads(sys.stdin.readline())
            self.assertEqual(message["text"], "你好🐾")
            sys.stdout.write(json.dumps(message, ensure_ascii=False) + "\n")
            sys.stdout.flush()
            sys.stderr.write("中文错误信息")
            sys.stderr.flush()
        self.assertEqual(json.loads(outgoing.getvalue().decode("utf-8")), message)
        self.assertEqual(errors.getvalue().decode("utf-8"), "中文错误信息")

    @unittest.skipUnless(sys.platform == "win32", "Requires Windows inherited pipe handles")
    def test_pythonw_recovers_missing_streams_without_allocating_a_console(self):
        pythonw = Path(sys.executable).with_name("pythonw.exe")
        self.assertTrue(pythonw.is_file())
        bootstrap = """
import ctypes
import json
import sys
from deskpaw.platform.windows_stdio import configure_mcp_stdio
sys.stdin = sys.stdout = sys.stderr = None
configure_mcp_stdio()
message = json.loads(sys.stdin.readline())
sys.stdout.write(json.dumps(message, ensure_ascii=False) + '\\n')
sys.stdout.flush()
sys.stderr.write('中文错误信息')
sys.stderr.flush()
assert not ctypes.WinDLL('kernel32').GetConsoleWindow()
"""
        message = {"text": "你好🐾"}
        result = subprocess.run(
            [str(pythonw), "-c", bootstrap],
            input=json.dumps(message, ensure_ascii=False) + "\n",
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=15,
            check=True,
        )
        self.assertEqual(json.loads(result.stdout), message)
        self.assertEqual(result.stderr, "中文错误信息")
