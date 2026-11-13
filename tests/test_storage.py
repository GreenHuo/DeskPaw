"""Persistence failure cases shared by settings, mood and desktop state."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from deskpaw.config import Settings
from deskpaw.core.storage import read_json_object, write_json_object


class StorageTests(unittest.TestCase):
    def test_invalid_and_non_object_json_fall_back_to_defaults(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "settings.json"
            self.assertEqual(read_json_object(path), {})
            for content in ("broken", "null", "[]", '"text"'):
                with self.subTest(content=content):
                    path.write_text(content, encoding="utf-8")
                    self.assertEqual(Settings.load(path), Settings())

    def test_failed_replace_preserves_old_file_and_removes_temporary_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "settings.json"
            Settings(pet_name="原来的名字").save(path)
            with patch.object(Path, "replace", side_effect=OSError("disk failure")):
                with self.assertRaises(OSError):
                    Settings(pet_name="新名字").save(path)
            self.assertEqual(Settings.load(path).pet_name, "原来的名字")
            self.assertEqual(list(path.parent.iterdir()), [path])

    def test_serialization_failure_does_not_touch_existing_data(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "state.json"
            write_json_object(path, {"name": "柯基"})
            with self.assertRaises(TypeError):
                write_json_object(path, {"invalid": object()})
            self.assertEqual(read_json_object(path), {"name": "柯基"})
