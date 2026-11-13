"""Locate bundled assets in source, installed wheels and PyInstaller bundles."""

from pathlib import Path

ASSET_DIRECTORY = Path(__file__).resolve().parents[1] / "assets"


def asset_path(name: str) -> Path:
    """Return a path to a bundled application asset."""
    return ASSET_DIRECTORY / name
