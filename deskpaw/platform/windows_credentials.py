"""Store API keys in the current Windows user's Credential Manager."""

from __future__ import annotations

import ctypes
import sys

DWORD = ctypes.c_uint32
LPBYTE = ctypes.POINTER(ctypes.c_ubyte)


class FILETIME(ctypes.Structure):
    _fields_ = [("low", DWORD), ("high", DWORD)]


class CREDENTIALW(ctypes.Structure):
    _fields_ = [
        ("Flags", DWORD),
        ("Type", DWORD),
        ("TargetName", ctypes.c_wchar_p),
        ("Comment", ctypes.c_wchar_p),
        ("LastWritten", FILETIME),
        ("CredentialBlobSize", DWORD),
        ("CredentialBlob", LPBYTE),
        ("Persist", DWORD),
        ("AttributeCount", DWORD),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", ctypes.c_wchar_p),
        ("UserName", ctypes.c_wchar_p),
    ]


class WindowsCredentials:
    def __init__(self) -> None:
        if sys.platform != "win32":
            raise OSError("Windows Credential Manager is only available on Windows")
        self.api = ctypes.WinDLL("Advapi32", use_last_error=True)
        pointer = ctypes.POINTER(CREDENTIALW)
        for name, result, arguments in (
            ("CredWriteW", ctypes.c_int32, [pointer, DWORD]),
            (
                "CredReadW",
                ctypes.c_int32,
                [ctypes.c_wchar_p, DWORD, DWORD, ctypes.POINTER(pointer)],
            ),
            ("CredDeleteW", ctypes.c_int32, [ctypes.c_wchar_p, DWORD, DWORD]),
            ("CredFree", None, [ctypes.c_void_p]),
        ):
            function = getattr(self.api, name)
            function.restype, function.argtypes = result, arguments

    @staticmethod
    def _error(operation: str) -> RuntimeError:
        code = ctypes.get_last_error()
        return RuntimeError(f"无法{operation} Windows 凭据（错误 {code}）")

    def read(self, target: str) -> str:
        pointer = ctypes.POINTER(CREDENTIALW)()
        if not self.api.CredReadW(target, 1, 0, ctypes.byref(pointer)):
            if ctypes.get_last_error() == 1168:
                return ""
            raise self._error("读取")
        try:
            credential = pointer.contents
            return ctypes.string_at(
                credential.CredentialBlob, credential.CredentialBlobSize
            ).decode("utf-8")
        finally:
            self.api.CredFree(pointer)

    def write(self, target: str, key: str) -> None:
        data = key.encode("utf-8")
        if len(data) > 2560:
            raise ValueError("API Key 超过 Windows 凭据存储支持的长度")
        blob = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
        credential = CREDENTIALW()
        credential.Type = 1
        credential.TargetName = target
        credential.Comment = "DeskPaw chat API key"
        credential.CredentialBlobSize = len(data)
        credential.CredentialBlob = ctypes.cast(blob, LPBYTE)
        credential.Persist = 2
        credential.UserName = "deskpaw"
        if not self.api.CredWriteW(ctypes.byref(credential), 0):
            raise self._error("保存")

    def delete(self, target: str) -> bool:
        if self.api.CredDeleteW(target, 1, 0):
            return True
        if ctypes.get_last_error() == 1168:
            return False
        raise self._error("删除")
