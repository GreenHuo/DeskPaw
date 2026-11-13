"""Stable user configuration locations."""

import os
import sys
from pathlib import Path


def settings_path() -> Path:
    if sys.platform == "win32":
        return (
            Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
            / "DeskPaw"
            / "settings.json"
        )
    return Path.home() / ".config" / "DeskPaw" / "settings.json"
