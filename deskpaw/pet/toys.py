"""Local light-point and hidden-snack game windows."""

from __future__ import annotations

import math

from PySide6.QtCore import QPoint, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QRadialGradient
from PySide6.QtWidgets import QHBoxLayout, QLabel, QToolButton, QVBoxLayout, QWidget


def toy_flags() -> Qt.WindowType:
    return (
        Qt.WindowType.FramelessWindowHint
        | Qt.WindowType.WindowStaysOnTopHint
        | Qt.WindowType.Tool
        | Qt.WindowType.NoDropShadowWindowHint
    )


class LightWindow(QWidget):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setWindowFlags(toy_flags() | Qt.WindowType.WindowTransparentForInput)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFixedSize(36, 28)
        self.phase = 0.0

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        gradient = QRadialGradient(18, 14, 14)
        gradient.setColorAt(0, QColor("#fff4aa"))
        gradient.setColorAt(0.25, QColor("#ff6d69"))
        gradient.setColorAt(1, QColor(255, 80, 80, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradient)
        radius = 11 + math.sin(self.phase * 7) * 2
        painter.drawEllipse(QRectF(18 - radius, 14 - radius * 0.6, radius * 2, radius * 1.2))


def cup_icon(opened: bool = False, found: bool = False) -> QIcon:
    pixmap = QPixmap(64, 48)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor("#a86c46"), 2))
    painter.setBrush(QColor("#f3c88e") if not opened else QColor("#ffe9c6"))
    painter.drawRoundedRect(QRectF(13, 8, 38, 31), 6, 6)
    painter.drawEllipse(QRectF(13, 5, 38, 12))
    if found:
        painter.setBrush(QColor("#ce8545"))
        painter.drawEllipse(QRectF(23, 18, 18, 16))
        painter.setBrush(QColor("#77462c"))
        for x, y in ((28, 23), (35, 27), (30, 30)):
            painter.drawEllipse(x, y, 2, 2)
    painter.end()
    return QIcon(pixmap)


class SnackWindow(QWidget):
    selected = Signal(int)

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setWindowFlags(toy_flags())
        self.setWindowTitle("DeskPaw 找零食")
        self.setFixedSize(294, 120)
        self.setStyleSheet(
            "SnackWindow { background: #fff5e5; border: 1px solid #d7b58d; border-radius: 12px; }"
            "QToolButton { background: #fffaf1; border: 1px solid #e5cbaa; border-radius: 8px; padding: 5px; }"
            "QToolButton:disabled { color: #88674c; }"
        )
        layout = QVBoxLayout(self)
        self.hint = QLabel("点杯子，让柯基闻闻零食藏在哪。")
        self.hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.hint)
        row = QHBoxLayout()
        self.cups = []
        for index in range(3):
            button = QToolButton()
            button.setText(f"杯子 {index + 1}")
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            button.setIcon(cup_icon())
            button.setIconSize(QSize(64, 48))
            button.clicked.connect(lambda checked=False, i=index: self.selected.emit(i))
            self.cups.append(button)
            row.addWidget(button)
        layout.addLayout(row)

    def reset(self) -> None:
        self.hint.setText("点杯子，让柯基闻闻零食藏在哪。")
        for index, button in enumerate(self.cups):
            button.setText(f"杯子 {index + 1}")
            button.setIcon(cup_icon())
            button.setEnabled(True)

    def reveal(self, index: int, found: bool) -> None:
        self.cups[index].setText("找到啦！" if found else "空杯子")
        self.cups[index].setIcon(cup_icon(True, found))
        self.cups[index].setEnabled(False)
        self.hint.setText("找到零食啦！" if found else "这个没有，再选一个杯子。")

    def target(self, index: int) -> QPoint:
        button = self.cups[index]
        return button.mapToGlobal(button.rect().center())
