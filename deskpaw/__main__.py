"""Run with `python -m deskpaw`."""

from __future__ import annotations

import sys

from deskpaw.knowledge import KnowledgeService


def main(*, knowledge: KnowledgeService | None = None) -> int:
    if "--mcp-excel-server" in sys.argv:
        from deskpaw.integrations.excel.server import main as excel_server_main

        return excel_server_main()

    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    from deskpaw.config import Settings
    from deskpaw.core.bond import Bond
    from deskpaw.core.desktop import DesktopState
    from deskpaw.core.resources import asset_path
    from deskpaw.pet.window import PetWindow
    from deskpaw.ui.controls import DesktopControls

    app = QApplication(sys.argv)
    app.setApplicationName("DeskPaw")
    app.setWindowIcon(QIcon(str(asset_path("deskpaw.ico"))))
    app.setQuitOnLastWindowClosed(False)
    pet = PetWindow(Settings.load(), Bond.load(), DesktopState.load(), knowledge=knowledge)
    pet.desktop_controls = DesktopControls(pet)
    app.aboutToQuit.connect(pet.shutdown)
    pet.show()
    pet.desktop_controls.start()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
