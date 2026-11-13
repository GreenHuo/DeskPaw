"""Visible Win32 program frames converted to Qt desktop coordinates."""

from __future__ import annotations

import ctypes
import os
import sys
from pathlib import PureWindowsPath

from PySide6.QtCore import QRect
from PySide6.QtWidgets import QApplication

LONG, DWORD, BOOL = ctypes.c_int32, ctypes.c_uint32, ctypes.c_int32
HANDLE = ctypes.c_void_p


class RECT(ctypes.Structure):
    _fields_ = [("left", LONG), ("top", LONG), ("right", LONG), ("bottom", LONG)]


class MONITORINFOEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", DWORD),
        ("rcMonitor", RECT),
        ("rcWork", RECT),
        ("dwFlags", DWORD),
        ("szDevice", ctypes.c_wchar * 32),
    ]


def logical_rect(rect: QRect, monitor: QRect, screen) -> QRect:
    """Anchor each display independently, including negative origins / mixed DPI."""
    ratio = screen.devicePixelRatio()
    origin = screen.geometry()
    return QRect(
        origin.x() + round((rect.x() - monitor.x()) / ratio),
        origin.y() + round((rect.y() - monitor.y()) / ratio),
        round(rect.width() / ratio),
        round(rect.height() / ratio),
    )


class WindowsWindows:
    def __init__(self) -> None:
        if sys.platform != "win32":
            raise OSError("Win32 window enumeration is only available on Windows")
        self.user = ctypes.WinDLL("user32", use_last_error=True)
        self.dwm = ctypes.WinDLL("dwmapi", use_last_error=True)
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.callback_type = ctypes.WINFUNCTYPE(BOOL, HANDLE, ctypes.c_ssize_t)
        for library, name, result, arguments in (
            (self.user, "EnumWindows", BOOL, [self.callback_type, ctypes.c_ssize_t]),
            (self.user, "IsWindowVisible", BOOL, [HANDLE]),
            (self.user, "IsIconic", BOOL, [HANDLE]),
            (self.user, "GetWindowThreadProcessId", DWORD, [HANDLE, ctypes.POINTER(DWORD)]),
            (self.user, "GetWindowRect", BOOL, [HANDLE, ctypes.POINTER(RECT)]),
            (
                self.user,
                "GetWindowTextW",
                ctypes.c_int32,
                [HANDLE, ctypes.c_wchar_p, ctypes.c_int32],
            ),
            (
                self.user,
                "GetClassNameW",
                ctypes.c_int32,
                [HANDLE, ctypes.c_wchar_p, ctypes.c_int32],
            ),
            (self.user, "GetWindowLongW", LONG, [HANDLE, ctypes.c_int32]),
            (self.user, "MonitorFromWindow", HANDLE, [HANDLE, DWORD]),
            (self.user, "GetMonitorInfoW", BOOL, [HANDLE, ctypes.POINTER(MONITORINFOEXW)]),
            (self.dwm, "DwmGetWindowAttribute", LONG, [HANDLE, DWORD, ctypes.c_void_p, DWORD]),
            (self.kernel, "OpenProcess", HANDLE, [DWORD, BOOL, DWORD]),
            (
                self.kernel,
                "QueryFullProcessImageNameW",
                BOOL,
                [HANDLE, DWORD, ctypes.c_wchar_p, ctypes.POINTER(DWORD)],
            ),
            (self.kernel, "CloseHandle", BOOL, [HANDLE]),
        ):
            function = getattr(library, name)
            function.restype, function.argtypes = result, arguments

    def _owner(self, pid: int) -> str:
        handle = self.kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return f"程序 {pid}"
        try:
            size = DWORD(32768)
            path = ctypes.create_unicode_buffer(size.value)
            if self.kernel.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(size)):
                return PureWindowsPath(path.value).stem
            return f"程序 {pid}"
        finally:
            self.kernel.CloseHandle(handle)

    def _rect(self, hwnd) -> QRect | None:
        rect = RECT()
        if self.dwm.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(rect), ctypes.sizeof(rect)) != 0:
            if not self.user.GetWindowRect(hwnd, ctypes.byref(rect)):
                return None
        physical = QRect(rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top)
        monitor = self.user.MonitorFromWindow(hwnd, 2)
        info = MONITORINFOEXW()
        info.cbSize = ctypes.sizeof(info)
        if monitor and self.user.GetMonitorInfoW(monitor, ctypes.byref(info)):
            screen = next(
                (
                    s
                    for s in QApplication.screens()
                    if s.name().casefold() == info.szDevice.casefold()
                ),
                None,
            )
            if screen:
                native = info.rcMonitor
                return logical_rect(
                    physical,
                    QRect(
                        native.left,
                        native.top,
                        native.right - native.left,
                        native.bottom - native.top,
                    ),
                    screen,
                )
        return physical

    def windows(self):
        from deskpaw.platform.surfaces import WindowSurface

        result, owners, failures = [], {}, []

        def visit(hwnd, _):
            try:
                if not self.user.IsWindowVisible(hwnd) or self.user.IsIconic(hwnd):
                    return True
                if self.user.GetWindowLongW(hwnd, -20) & 0x80:
                    return True
                cloaked = DWORD()
                if (
                    self.dwm.DwmGetWindowAttribute(
                        hwnd, 14, ctypes.byref(cloaked), ctypes.sizeof(cloaked)
                    )
                    == 0
                    and cloaked.value
                ):
                    return True
                class_name = ctypes.create_unicode_buffer(256)
                self.user.GetClassNameW(hwnd, class_name, len(class_name))
                if class_name.value in {
                    "Progman",
                    "WorkerW",
                    "Shell_TrayWnd",
                    "Shell_SecondaryTrayWnd",
                }:
                    return True
                pid = DWORD()
                self.user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if pid.value == os.getpid() or not pid.value:
                    return True
                rect = self._rect(hwnd)
                if rect is None or rect.width() < 180 or rect.height() < 80:
                    return True
                title = ctypes.create_unicode_buffer(1024)
                self.user.GetWindowTextW(hwnd, title, len(title))
                if pid.value not in owners:
                    owners[pid.value] = self._owner(pid.value)
                result.append(
                    WindowSurface(int(hwnd), pid.value, owners[pid.value], title.value, rect)
                )
                return True
            except (OSError, ValueError) as exc:
                failures.append(exc)
                return False

        callback = self.callback_type(visit)
        if not self.user.EnumWindows(callback, 0):
            raise OSError("无法枚举 Windows 程序窗口") from (failures[0] if failures else None)
        return result
