"""Offline startup check used to validate a packaged application."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import traceback
import uuid
from pathlib import Path


def _check_excel_server() -> None:
    from openpyxl import Workbook

    from deskpaw.integrations.mcp.stdio import MCPClient

    command = [sys.executable]
    if not getattr(sys, "frozen", False):
        command.extend(["-m", "deskpaw"])
    command.append("--mcp-excel-server")
    with tempfile.TemporaryDirectory(prefix="DeskPaw-excel-selftest-") as directory:
        source = Path(directory) / "销售.xlsx"
        book = Workbook()
        book.active.title = "销售"
        book.active.append(["月份", "销售额"])
        book.active.append(["一月", 120])
        book.save(source)
        book.close()
        with MCPClient(command, {"DESKPAW_WORKBOOK_PATH": str(source)}) as client:
            names = {tool["name"] for tool in client.list_tools()}
            assert {
                "inspect_workbook",
                "preview_sheet",
                "aggregate_sheet",
                "create_summary",
            } <= names
            result = client.call_tool("preview_sheet", {"sheet_name": "销售", "limit": 1})
            assert not result.get("isError"), result
            preview = json.loads(result["content"][0]["text"])
            assert preview["headers"] == ["月份", "销售额"], preview
            assert preview["rows"] == [["一月", 120]], preview


def run(report: Path) -> int:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6.QtGui import QPixmap
    from PySide6.QtWidgets import QApplication

    from deskpaw.config import Settings
    from deskpaw.core.resources import ASSET_DIRECTORY
    from deskpaw.pet.window import PetWindow
    from deskpaw.platform.surfaces import WindowProvider
    from deskpaw.ui.chat import ChatDialog
    from deskpaw.ui.controls import DesktopControls

    app = QApplication([])
    checks, windows, error = [], [], ""
    try:
        assets = ASSET_DIRECTORY
        pngs = list(assets.glob("*.png"))
        assert pngs and all(not QPixmap(str(p)).isNull() for p in pngs), (
            "Missing or unreadable sprites"
        )
        assert (assets / "ui-check.svg").is_file(), "Missing UI checkbox icon"
        checks.append("bundled-assets")
        pet = PetWindow(Settings(roam=False), window_provider=WindowProvider(enabled=False))
        controls = DesktopControls(pet)
        pet.desktop_controls = controls
        chat = ChatDialog(pet.settings)
        windows = [pet, controls.panel, chat]
        for window in windows:
            window.show()
        app.processEvents()
        assert all(not w.grab().isNull() for w in windows), "Unable to render UI"
        checks.append("pet-management-chat-render")
        pet.move(app.primaryScreen().availableGeometry().center())
        pet.dragging = True
        pet._finish_drag()
        assert pet.drop_from_y is None and pet.height() == pet.normal_height
        checks.append("stationary-placement")
        _check_excel_server()
        checks.append("excel-mcp-subprocess")
        if sys.platform == "win32":
            from deskpaw.platform.windows_credentials import WindowsCredentials
            from deskpaw.platform.windows_surfaces import WindowsWindows

            WindowsWindows().windows()
            checks.append("win32-window-api")
            store = WindowsCredentials()
            target = "DeskPaw/selftest/" + uuid.uuid4().hex
            try:
                store.write(target, "deskpaw-dummy-key")
                assert store.read(target) == "deskpaw-dummy-key"
                store.delete(target)
                assert store.read(target) == ""
                checks.append("windows-credential-manager")
            finally:
                store.delete(target)
        pet.shutdown()
    except Exception:
        error = traceback.format_exc()
    finally:
        for window in windows:
            window.close()
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(
            json.dumps(
                {"ok": not error, "platform": sys.platform, "checks": checks, "error": error},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    return 1 if error else 0
