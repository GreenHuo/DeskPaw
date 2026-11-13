"""Native macOS check: an inactive pet stays visible and follows a moving window.

Run from the project with .venv/bin/python scripts/check-macos-perch.py.
Use --before to reproduce the original Qt tool-panel hiding behavior.
Only temporary test windows are created; no settings or screen pixels are read.
"""

import ctypes
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QWidget


def activate():
    objc = ctypes.CDLL("/usr/lib/libobjc.A.dylib")
    objc.objc_getClass.argtypes = [ctypes.c_char_p]
    objc.objc_getClass.restype = ctypes.c_void_p
    objc.sel_registerName.argtypes = [ctypes.c_char_p]
    objc.sel_registerName.restype = ctypes.c_void_p
    address = ctypes.cast(objc.objc_msgSend, ctypes.c_void_p).value
    get = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)(address)
    call = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_bool)(address)
    app = get(objc.objc_getClass(b"NSApplication"), objc.sel_registerName(b"sharedApplication"))
    call(app, objc.sel_registerName(b"activateIgnoringOtherApps:"), True)


app = QApplication([])
app.setQuitOnLastWindowClosed(False)
if "--child" in sys.argv:
    window = QWidget()
    window.setWindowTitle("DeskPaw focus and movement check")
    window.setGeometry(180, 360, 520, 240)
    window.show()
    QTimer.singleShot(500, activate)
    for step in range(1, 9):
        QTimer.singleShot(900 + step * 180, lambda s=step: window.move(180 + s * 14, 360 + s * 5))
    QTimer.singleShot(3500, app.quit)
    sys.exit(app.exec())

from PySide6.QtCore import Qt

from deskpaw.config import Settings
from deskpaw.pet.window import PetWindow
from deskpaw.platform.surfaces import WindowProvider

provider = WindowProvider()
pet = PetWindow(Settings(roam=False), window_provider=provider)
if "--before" in sys.argv:
    pet.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow, False)
pet.show()
activate()
child = None
errors = []
samples = []
positions = set()


def visible_native_pet():
    native = provider.native
    array = native.cg.CGWindowListCopyWindowInfo(1 | 16, 0)
    try:
        for index in range(native.cf.CFArrayGetCount(array)):
            info = native.cf.CFArrayGetValueAtIndex(array, index)
            if (
                int(native._number(info, "kCGWindowOwnerPID")) == os.getpid()
                and native._number(info, "kCGWindowAlpha") > 0
            ):
                return True
        return False
    finally:
        native.cf.CFRelease(array)


def launch():
    global child
    child = subprocess.Popen([sys.executable, __file__, "--child"])


def check():
    try:
        if child is None or child.poll() is not None:
            return
        surface = next((w for w in provider.windows() if w.pid == child.pid), None)
        if surface is None:
            return
        if pet.perch is None:
            pet.perch_on(surface, 0.4)
        pet._follow_perch()
        positions.add((pet.x(), pet.y()))
        if app.applicationState() == Qt.ApplicationState.ApplicationInactive:
            samples.append(visible_native_pet())
    except Exception as exc:
        errors.append(repr(exc))
        app.quit()


QTimer.singleShot(500, launch)
timer = QTimer()
timer.timeout.connect(check)
timer.start(100)
QTimer.singleShot(3700, app.quit)
app.exec()
pet.shutdown()
pet.close()
if child is not None:
    child.wait(timeout=2)
print(
    json.dumps(
        {
            "baseline": "--before" in sys.argv,
            "inactive_samples": len(samples),
            "visible_samples": sum(samples),
            "positions_followed": len(positions),
            "errors": errors,
        }
    )
)
assert not errors and len(samples) > 8 and len(positions) > 3
if "--before" in sys.argv:
    assert not any(samples), "Expected original tool panel to disappear when inactive"
else:
    assert all(samples), "Pet disappeared while another application was active"
