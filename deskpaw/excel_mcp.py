"""Compatibility entry point for ``python -m deskpaw.excel_mcp``."""

from deskpaw.integrations.excel.server import main

if __name__ == "__main__":
    raise SystemExit(main())
