import ctypes
import os
import sys
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QRect

from deskpaw.config import (
    delete_api_key,
    get_api_key,
    save_api_key,
    settings_path,
)
from deskpaw.platform.windows_credentials import CREDENTIALW, WindowsCredentials
from deskpaw.platform.windows_surfaces import RECT, logical_rect


class Screen:
    def geometry(self):
        return QRect(-1600, -100, 1600, 900)

    def devicePixelRatio(self):
        return 1.5


class WindowsPlatformTests(unittest.TestCase):
    def test_windows_config_path_and_vault_routing_are_service_specific(self):
        with (
            patch("deskpaw.config.credentials.sys.platform", "win32"),
            patch.dict(os.environ, {"APPDATA": "C:/User/AppData/Roaming"}, clear=True),
            patch("deskpaw.platform.windows_credentials.WindowsCredentials") as vault,
        ):
            self.assertEqual(settings_path(), Path("C:/User/AppData/Roaming/DeskPaw/settings.json"))
            vault.return_value.read.return_value = "dummy-key"
            self.assertEqual(get_api_key("https://api.deepseek.com"), "dummy-key")
            save_api_key("https://api.deepseek.com", "new-dummy-key")
            self.assertTrue(delete_api_key("https://api.deepseek.com"))
            target = vault.return_value.read.call_args.args[0]
            self.assertEqual(vault.return_value.write.call_args.args, (target, "new-dummy-key"))
            self.assertEqual(vault.return_value.delete.call_args.args, (target,))
            get_api_key("https://another.example/v1")
            self.assertNotEqual(vault.return_value.read.call_args.args[0], target)

    def test_windows_physical_coordinates_convert_for_negative_origin_and_mixed_dpi(self):
        frame = logical_rect(QRect(-2100, 200, 900, 600), QRect(-2400, -300, 2400, 1350), Screen())
        self.assertEqual(frame, QRect(-1400, 233, 600, 400))
        self.assertEqual(ctypes.sizeof(RECT), 16)

    @unittest.skipUnless(sys.platform == "win32", "Requires native Windows credential APIs")
    def test_native_credentials_round_trip_replace_and_delete(self):
        store = WindowsCredentials()
        target = "DeskPaw/unit-test/" + uuid.uuid4().hex
        try:
            self.assertEqual(store.read(target), "")
            store.write(target, "dummy-key-中文")
            self.assertEqual(store.read(target), "dummy-key-中文")
            store.write(target, "replacement-dummy")
            self.assertEqual(store.read(target), "replacement-dummy")
            self.assertTrue(store.delete(target))
            self.assertFalse(store.delete(target))
        finally:
            store.delete(target)
        self.assertEqual(ctypes.sizeof(CREDENTIALW), 80)
