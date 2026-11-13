"""Keep the bundled MCP server usable in a Windows GUI executable."""

from __future__ import annotations

import ctypes
import os
import sys


def _inherited_stream(identifier: int, mode: str):
    import msvcrt

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    handle_type = ctypes.c_void_p
    kernel.GetStdHandle.argtypes = [ctypes.c_uint32]
    kernel.GetStdHandle.restype = handle_type
    kernel.GetCurrentProcess.argtypes = []
    kernel.GetCurrentProcess.restype = handle_type
    kernel.DuplicateHandle.argtypes = [
        handle_type,
        handle_type,
        handle_type,
        ctypes.POINTER(handle_type),
        ctypes.c_uint32,
        ctypes.c_int32,
        ctypes.c_uint32,
    ]
    kernel.DuplicateHandle.restype = ctypes.c_int32
    kernel.CloseHandle.argtypes = [handle_type]
    kernel.CloseHandle.restype = ctypes.c_int32

    handle = kernel.GetStdHandle(identifier)
    if handle in (None, ctypes.c_void_p(-1).value):
        raise OSError("The MCP server requires redirected standard input and output.")
    duplicate = handle_type()
    process = kernel.GetCurrentProcess()
    if not kernel.DuplicateHandle(process, handle, process, ctypes.byref(duplicate), 0, False, 2):
        raise ctypes.WinError(ctypes.get_last_error())
    flags = (os.O_RDONLY if mode == "r" else os.O_WRONLY) | os.O_BINARY
    try:
        descriptor = msvcrt.open_osfhandle(duplicate.value, flags)
    except OSError:
        kernel.CloseHandle(duplicate)
        raise
    try:
        return os.fdopen(descriptor, mode, encoding="utf-8", buffering=1)
    except Exception:
        os.close(descriptor)
        raise


def configure_mcp_stdio() -> None:
    """Restore inherited pipes when Python has no console, using UTF-8 JSON."""
    if sys.platform != "win32":
        return
    for name, identifier, mode in (("stdin", -10, "r"), ("stdout", -11, "w"), ("stderr", -12, "w")):
        stream = getattr(sys, name)
        if stream is None:
            stream = _inherited_stream(identifier, mode)
            setattr(sys, name, stream)
            setattr(sys, f"__{name}__", stream)
        elif hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
