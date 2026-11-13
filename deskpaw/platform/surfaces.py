"""Read native window frames for pet perching; never capture window pixels."""

from __future__ import annotations

import ctypes
import os
import sys
from dataclasses import dataclass

from PySide6.QtCore import QRect


@dataclass(frozen=True)
class WindowSurface:
    identifier: int
    pid: int
    owner: str
    title: str
    rect: QRect

    @property
    def label(self) -> str:
        return self.owner + (
            f" · {self.title[:38]}" if self.title else f" · 窗口 {self.identifier}"
        )


class WindowProvider:
    def __init__(self, enabled: bool = True) -> None:
        self.error = ""
        self.native = None
        if not enabled:
            self.error = "当前图形环境无法读取程序窗口"
        elif sys.platform == "darwin":
            try:
                self.native = MacWindows()
            except (OSError, AttributeError) as exc:
                self.error = f"暂时无法读取窗口位置：{exc}"
        elif sys.platform == "win32":
            try:
                from deskpaw.platform.windows_surfaces import WindowsWindows

                self.native = WindowsWindows()
            except (OSError, AttributeError) as exc:
                self.error = f"暂时无法读取窗口位置：{exc}"
        else:
            self.error = "当前系统尚不支持识别其他程序窗口"

    def windows(self) -> list[WindowSurface]:
        if self.native is None:
            return []
        try:
            windows = self.native.windows()
            self.error = ""
            return windows
        except (OSError, ValueError) as exc:
            self.error = f"暂时无法读取窗口位置：{exc}"
            return []


class MacWindows:
    """Core Graphics / Core Foundation bridge with owned references released."""

    def __init__(self) -> None:
        self.cf = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
        self.cg = ctypes.CDLL("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
        ptr = ctypes.c_void_p
        self._declare(
            self.cg, "CGWindowListCopyWindowInfo", ptr, [ctypes.c_uint32, ctypes.c_uint32]
        )
        self._declare(self.cf, "CFArrayGetCount", ctypes.c_long, [ptr])
        self._declare(self.cf, "CFArrayGetValueAtIndex", ptr, [ptr, ctypes.c_long])
        self._declare(self.cf, "CFDictionaryGetValue", ptr, [ptr, ptr])
        self._declare(
            self.cf, "CFStringCreateWithCString", ptr, [ptr, ctypes.c_char_p, ctypes.c_uint32]
        )
        self._declare(
            self.cf, "CFStringGetCString", ctypes.c_bool, [ptr, ptr, ctypes.c_long, ctypes.c_uint32]
        )
        self._declare(self.cf, "CFNumberGetValue", ctypes.c_bool, [ptr, ctypes.c_int, ptr])
        self._declare(self.cf, "CFGetTypeID", ctypes.c_ulong, [ptr])
        for name in ("CFStringGetTypeID", "CFNumberGetTypeID", "CFDictionaryGetTypeID"):
            self._declare(self.cf, name, ctypes.c_ulong, [])
        self._declare(self.cf, "CFRelease", None, [ptr])

    @staticmethod
    def _declare(lib, name, result, args) -> None:
        function = getattr(lib, name)
        function.restype, function.argtypes = result, args

    def _get(self, dictionary, key: str):
        if not dictionary:
            return None
        key_ref = self.cf.CFStringCreateWithCString(None, key.encode(), 0x08000100)
        try:
            return self.cf.CFDictionaryGetValue(dictionary, key_ref)
        finally:
            self.cf.CFRelease(key_ref)

    def _number(self, dictionary, key: str) -> float:
        value = self._get(dictionary, key)
        if not value or self.cf.CFGetTypeID(value) != self.cf.CFNumberGetTypeID():
            return 0
        number = ctypes.c_double()
        self.cf.CFNumberGetValue(value, 6, ctypes.byref(number))
        return number.value

    def _string(self, dictionary, key: str) -> str:
        value = self._get(dictionary, key)
        if not value or self.cf.CFGetTypeID(value) != self.cf.CFStringGetTypeID():
            return ""
        buffer = ctypes.create_string_buffer(4096)
        if not self.cf.CFStringGetCString(value, buffer, len(buffer), 0x08000100):
            return ""
        return buffer.value.decode("utf-8", errors="replace")

    def windows(self) -> list[WindowSurface]:
        array = self.cg.CGWindowListCopyWindowInfo(1 | 16, 0)
        if not array:
            raise OSError("无法连接 macOS 窗口服务，请从桌面图形会话启动")
        result = []
        try:
            for index in range(self.cf.CFArrayGetCount(array)):
                info = self.cf.CFArrayGetValueAtIndex(array, index)
                pid = int(self._number(info, "kCGWindowOwnerPID"))
                if pid == os.getpid() or self._number(info, "kCGWindowLayer") != 0:
                    continue
                bounds = self._get(info, "kCGWindowBounds")
                if not bounds or self.cf.CFGetTypeID(bounds) != self.cf.CFDictionaryGetTypeID():
                    continue
                rect = QRect(
                    *(round(self._number(bounds, key)) for key in ("X", "Y", "Width", "Height"))
                )
                if (
                    rect.width() < 180
                    or rect.height() < 80
                    or self._number(info, "kCGWindowAlpha") <= 0
                ):
                    continue
                result.append(
                    WindowSurface(
                        int(self._number(info, "kCGWindowNumber")),
                        pid,
                        self._string(info, "kCGWindowOwnerName") or "程序",
                        self._string(info, "kCGWindowName"),
                        rect,
                    )
                )
        finally:
            self.cf.CFRelease(array)
        return result
