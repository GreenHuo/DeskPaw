"""Small draggable ball used by the fetch game."""

from __future__ import annotations

import math
import time
from collections import deque

from PySide6.QtCore import QPoint, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget


class ThrowMotion:
    """Estimate the final 120ms of hand motion in screen pixels/second."""

    def __init__(self) -> None:
        self.samples: deque[tuple[float, float, float]] = deque(maxlen=32)

    def sample(self, x: float, y: float, now: float) -> None:
        self.samples.append((now, x, y))
        while len(self.samples) > 2 and self.samples[1][0] < now - 0.12:
            self.samples.popleft()

    def velocity(self, now: float) -> tuple[float, float]:
        recent = list(self.samples)
        if len(recent) < 2 or now - recent[-1][0] > 0.12:
            return 0.0, 0.0
        first, last = recent[0], recent[-1]
        cutoff = now - 0.12
        if first[0] < cutoff and recent[1][0] > first[0]:
            second = recent[1]
            fraction = max(0.0, min(1.0, (cutoff - first[0]) / (second[0] - first[0])))
            first = (
                cutoff,
                first[1] + (second[1] - first[1]) * fraction,
                first[2] + (second[2] - first[2]) * fraction,
            )
        dt = last[0] - first[0]
        if dt < 0.008:
            return 0.0, 0.0
        vx, vy = (last[1] - first[1]) / dt, (last[2] - first[2]) / dt
        speed = math.hypot(vx, vy)
        factor = min(1.0, 1800 / speed) if speed else 1.0
        return vx * factor, vy * factor


class BallWindow(QWidget):
    grabbed = Signal()
    released = Signal(float, float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(32, 32)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self._drag_offset: QPoint | None = None
        self.motion = ThrowMotion()
        self.kind = "ball"
        self.spin = 0.0
        self.setWindowTitle("DeskPaw 玩具")

    def set_kind(self, kind: str) -> None:
        self.kind = kind
        self._drag_offset = None
        self.setFixedSize(52 if kind == "frisbee" else 32, 32)
        self.setToolTip("拖动后甩手松开，方向和力度随鼠标速度变化")
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        painter = QPainter(self)
        painter.setCompositionMode(QPainter.CompositionMode_Source)
        painter.fillRect(self.rect(), Qt.GlobalColor.transparent)
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.kind == "frisbee":
            painter.translate(self.width() / 2, self.height() / 2)
            painter.rotate(math.sin(self.spin) * 12)
            painter.setBrush(QColor("#55cbd3"))
            painter.setPen(QPen(QColor("#207c91"), 2))
            painter.drawEllipse(QRectF(-24, -10, 48, 20))
            painter.setBrush(QColor("#a9edf0"))
            painter.drawEllipse(QRectF(-15, -6, 30, 12))
            return
        gradient = QRadialGradient(11, 9, 21)
        gradient.setColorAt(0, QColor("#ffcf86"))
        gradient.setColorAt(0.5, QColor("#f3934d"))
        gradient.setColorAt(1, QColor("#bd4e2c"))
        painter.setBrush(gradient)
        painter.setPen(QPen(QColor("#9b452b"), 1.4))
        painter.drawEllipse(QRectF(2, 2, 28, 28))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor("#fff2cf"), 2.2))
        painter.drawArc(QRectF(7, 6, 18, 20), 35 * 16, 190 * 16)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.pos()
            self.motion = ThrowMotion()
            point = event.globalPosition()
            self.motion.sample(point.x(), point.y(), time.monotonic())
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            self.grabbed.emit()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            point = event.globalPosition()
            self.motion.sample(point.x(), point.y(), time.monotonic())
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.MouseButton.LeftButton and self._drag_offset is not None:
            now = time.monotonic()
            point = event.globalPosition()
            self.motion.sample(point.x(), point.y(), now)
            self.move(point.toPoint() - self._drag_offset)
            self._drag_offset = None
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            self.released.emit(*self.motion.velocity(now))
            event.accept()
        else:
            super().mouseReleaseEvent(event)
