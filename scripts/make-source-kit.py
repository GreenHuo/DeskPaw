"""Bundle the Windows build sources without user data or local environments."""

import zipfile
from pathlib import Path

root = Path(__file__).resolve().parent.parent
output = root / "dist" / "DeskPaw-Windows-source.zip"
output.parent.mkdir(exist_ok=True)
files = [
    root / name
    for name in ("README.md", "pyproject.toml", "requirements.txt", "run-windows.bat", ".gitignore")
]
for name in ("deskpaw", "tests", "packaging", "scripts", ".github", "docs"):
    files.extend(
        path
        for path in (root / name).rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix != ".pyc"
        and path.name != ".DS_Store"
    )
with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
    for path in sorted(files):
        archive.write(path, "DeskPaw/" + path.relative_to(root).as_posix())
with zipfile.ZipFile(output) as archive:
    assert archive.testzip() is None
    assert "DeskPaw/packaging/DeskPaw.spec" in archive.namelist()
print(output)
