# Build this specification with Windows x64 Python.
from pathlib import Path

root = Path(SPECPATH).parent
analysis = Analysis(
    [str(root / 'packaging' / 'windows_entry.py')],
    pathex=[str(root)],
    binaries=[],
    datas=[(str(root / 'deskpaw' / 'assets'), 'deskpaw/assets')],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=['tkinter', 'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets'],
    noarchive=False,
)
pyz = PYZ(analysis.pure)
exe = EXE(
    pyz, analysis.scripts, analysis.binaries, analysis.datas, [],
    name='DeskPaw', debug=False, bootloader_ignore_signals=False,
    strip=False, upx=False, console=False, disable_windowed_traceback=False,
    icon=str(root / 'deskpaw' / 'assets' / 'deskpaw.ico'),
    version=str(root / 'packaging' / 'windows-version.txt'),
)
