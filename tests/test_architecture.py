"""Enforce headless extension boundaries and supported command entry points."""

import ast
import json
import subprocess
import sys
import unittest
from pathlib import Path


class ArchitectureTests(unittest.TestCase):
    def test_backend_layers_do_not_import_application_widgets(self):
        package = Path(__file__).resolve().parents[1] / "deskpaw"
        for layer in ("core", "config", "services", "integrations", "knowledge", "platform"):
            for source in (package / layer).rglob("*.py"):
                tree = ast.parse(source.read_text(encoding="utf-8"))
                for node in ast.walk(tree):
                    if isinstance(node, ast.ImportFrom):
                        imports = [node.module or ""]
                    elif isinstance(node, ast.Import):
                        imports = [alias.name for alias in node.names]
                    else:
                        continue
                    for name in imports:
                        with self.subTest(source=source.name, imported=name):
                            self.assertFalse(name.startswith(("deskpaw.ui", "deskpaw.pet")))
                            if layer in {"services", "integrations", "knowledge", "config"}:
                                self.assertFalse(name.startswith("PySide6"))

    def test_excel_entry_points_work_without_loading_qt(self):
        bootstrap = """
import builtins
import runpy
import sys
original_import = builtins.__import__
def headless_import(name, *args, **kwargs):
    if name.startswith('PySide6'):
        raise ImportError('Qt must not be loaded by a headless MCP server')
    return original_import(name, *args, **kwargs)
builtins.__import__ = headless_import
module = sys.argv[1]
sys.argv = [module, '--mcp-excel-server']
runpy.run_module(module, run_name='__main__')
"""
        request = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"}) + "\n"
        for module in ("deskpaw", "deskpaw.excel_mcp", "deskpaw.integrations.excel.server"):
            with self.subTest(module=module):
                result = subprocess.run(
                    [sys.executable, "-c", bootstrap, module],
                    input=request,
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=True,
                )
                response = json.loads(result.stdout)
                self.assertEqual(response["result"]["serverInfo"]["name"], "DeskPaw Excel")
