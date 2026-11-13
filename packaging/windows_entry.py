"""Absolute package imports allow PyInstaller to start DeskPaw correctly."""

import sys
from pathlib import Path

if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if "--self-test" in sys.argv:
    from deskpaw.selftest import run

    try:
        report_index = sys.argv.index("--report") + 1
        report = Path(sys.argv[report_index])
    except (ValueError, IndexError):
        report = Path.home() / "DeskPaw-self-test.json"
    raise SystemExit(run(report))

if "--mcp-excel-server" in sys.argv:
    from deskpaw.integrations.excel.server import main as excel_server_main

    raise SystemExit(excel_server_main())

from deskpaw.__main__ import main

raise SystemExit(main())
