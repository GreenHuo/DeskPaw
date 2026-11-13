@echo off
cd /d "%~dp0"
if not exist ".venv-win\Scripts\pythonw.exe" (
  echo Please run scripts\build-windows.ps1 first, or install Python dependencies in .venv-win.
  pause
  exit /b 1
)
start "" ".venv-win\Scripts\pythonw.exe" -m deskpaw
