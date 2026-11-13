"""Monitor-relative placement and desktop control preferences."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from pathlib import Path

from PySide6.QtCore import QPoint, QSize

from deskpaw.config.paths import settings_path

from .storage import read_json_object, write_json_object


@dataclass
class DesktopState:
    screen_name: str = ""
    screen_serial: str = ""
    screen_x: int = 0
    screen_y: int = 0
    x: float = 0.8
    y: float = 1.0
    positioned: bool = False
    paused: bool = False
    locked: bool = False
    perch_id: int = 0
    perch_pid: int = 0
    perch_ratio: float = 0.5
    path: Path | None = field(default=None, repr=False, compare=False)

    @classmethod
    def load(cls, path: Path | None = None) -> DesktopState:
        path = path or settings_path().with_name("desktop.json")
        data = read_json_object(path)
        return cls(
            screen_name=str(data.get("screen_name", "")),
            screen_serial=str(data.get("screen_serial", "")),
            screen_x=_coordinate(data.get("screen_x")),
            screen_y=_coordinate(data.get("screen_y")),
            x=_fraction(data.get("x"), 0.8),
            y=_fraction(data.get("y"), 1.0),
            positioned=data.get("positioned") is True,
            paused=data.get("paused") is True,
            locked=data.get("locked") is True,
            perch_id=_identifier(data.get("perch_id")),
            perch_pid=_identifier(data.get("perch_pid")),
            perch_ratio=_fraction(data.get("perch_ratio"), 0.5),
            path=path,
        )

    def capture(self, screen, position: QPoint, size: QSize) -> None:
        rect = screen.availableGeometry()
        self.screen_name = screen.name()
        self.screen_serial = screen.serialNumber()
        self.screen_x = screen.geometry().x()
        self.screen_y = screen.geometry().y()
        self.x = _fraction((position.x() - rect.left()) / max(1, rect.width() - size.width()), 0.8)
        self.y = _fraction((position.y() - rect.top()) / max(1, rect.height() - size.height()), 1.0)
        self.positioned = True

    def restore(self, screens, size: QSize) -> QPoint:
        screen = next(
            (s for s in screens if self.screen_serial and s.serialNumber() == self.screen_serial),
            None,
        )
        if screen is None:
            matching = [s for s in screens if s.name() == self.screen_name]
            screen = (
                min(
                    matching,
                    key=lambda s: (
                        abs(s.geometry().x() - self.screen_x)
                        + abs(s.geometry().y() - self.screen_y)
                    ),
                )
                if matching
                else screens[0]
            )
        rect = screen.availableGeometry()
        return QPoint(
            rect.left() + round(self.x * max(0, rect.width() - size.width())),
            rect.top() + round(self.y * max(0, rect.height() - size.height())),
        )

    def save(self) -> None:
        if self.path is None:
            return
        data = asdict(self)
        data.pop("path")
        write_json_object(self.path, data)


def _fraction(value: object, default: float) -> float:
    try:
        number = float(value)
        return max(0, min(1, number)) if math.isfinite(number) else default
    except (TypeError, ValueError, OverflowError):
        return default


def _identifier(value: object) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError, OverflowError):
        return 0


def _coordinate(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return 0
