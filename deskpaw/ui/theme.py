"""Shared palette, icons and small components for DeskPaw windows."""

from __future__ import annotations

import sys
from functools import lru_cache

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout

from deskpaw.core.resources import asset_path

STYLE = """
QDialog { background: #f7f5f0; }
QWidget { color: #302c28; font-family: 'PingFang SC'; font-size: 13px; }
QLabel { background: transparent; }
QLabel#Title { font-size: 22px; font-weight: 600; }
QLabel#SectionTitle { font-size: 14px; font-weight: 600; }
QLabel#Muted { color: #817b72; font-size: 12px; }
QLabel#Badge { color: #9b623c; background: #f7e8d7; border-radius: 10px; padding: 4px 10px; font-size: 11px; }
QFrame#EmotionBadge { background: #f7e8d7; border: none; border-radius: 9px; }
QFrame#EmotionBadge QLabel { color: #9b623c; font-size: 11px; }
QFrame#Card { background: #ffffff; border: 1px solid #e9e4db; border-radius: 14px; }
QPushButton, QToolButton { background: #ffffff; border: 1px solid #e4ded3; border-radius: 9px; padding: 9px 13px; font-weight: 500; }
QPushButton:hover, QToolButton:hover { background: #fff5e8; border-color: #d3b18d; }
QPushButton:pressed, QToolButton:pressed { background: #f5e7d5; }
QPushButton:disabled, QToolButton:disabled { color: #a7a196; background: #f1eee8; border-color: #e8e3da; }
QPushButton#Primary { background: #c97b43; color: white; border-color: #c97b43; }
QPushButton#Primary:hover { background: #b86b35; border-color: #b86b35; }
QPushButton#Primary:disabled { background: #d9b79d; border-color: #d9b79d; color: #fff8f2; }
QPushButton#Quiet { background: transparent; border-color: transparent; color: #817b72; }
QPushButton#Quiet:hover { background: #ece7de; color: #302c28; }
QPushButton#GameTile { text-align: left; padding: 0; background: #fff; border-radius: 12px; }
QPushButton#GameTile:hover { background: #fff6eb; }
QPushButton#Chip { padding: 6px 11px; font-size: 12px; background: #f0ece4; border: none; border-radius: 12px; }
QPushButton#Chip:hover { background: #f5e3ce; }
QLineEdit, QPlainTextEdit, QSpinBox { background: #ffffff; border: 1px solid #e4ded3; border-radius: 9px; padding: 9px 11px; selection-background-color: #eed0ad; color: #302c28; }
QLineEdit:focus, QPlainTextEdit:focus, QSpinBox:focus { border-color: #c97b43; }
QScrollArea { background: transparent; border: none; }
QScrollArea > QWidget > QWidget { background: transparent; }
QScrollBar:vertical { background: transparent; width: 7px; margin: 4px 0; }
QScrollBar::handle:vertical { background: #d9d2c7; border-radius: 3px; min-height: 28px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QTabWidget::pane { border: none; margin-top: 14px; }
QTabBar::tab { padding: 9px 21px; background: #ece7de; color: #817b72; border-radius: 8px; margin-right: 6px; }
QTabBar::tab:selected { background: #ffffff; color: #9b623c; }
QCheckBox { spacing: 9px; padding: 5px 0; }
QCheckBox::indicator { width: 17px; height: 17px; border: 1px solid #d8cfc1; border-radius: 5px; background: white; }
QCheckBox::indicator:checked { background: #c97b43; border: 4px solid #f0d4b9; }
QSlider::groove:horizontal { height: 5px; background: #e9e2d7; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #c97b43; border-radius: 2px; }
QSlider::handle:horizontal { width: 16px; margin: -6px 0; border: 1px solid #c97b43; border-radius: 8px; background: #fff; }
QProgressBar { border: none; background: #eee8de; border-radius: 3px; max-height: 6px; }
QProgressBar::chunk { background: #d49865; border-radius: 3px; }
QProgressBar#Closeness::chunk { background: #99a78d; }
QMenu { background: #fffdf9; border: 1px solid #e4ded3; border-radius: 9px; padding: 6px; }
QMenu::item { padding: 7px 25px 7px 10px; border-radius: 5px; }
QMenu::item:selected { background: #f3e2cf; }
QMenu::item:disabled { color: #968e83; }
QMenu::separator { height: 1px; background: #e9e3d9; margin: 5px 8px; }
"""


STYLE += (
    'QCheckBox::indicator:checked { border: 1px solid #c97b43; image: url("'
    + str(asset_path("ui-check.svg"))
    + '"); }'
)
STYLE = STYLE.replace(str(asset_path("ui-check.svg")), (asset_path("ui-check.svg")).as_posix())
if sys.platform == "win32":
    STYLE = STYLE.replace("'PingFang SC'", "'Microsoft YaHei UI', 'Segoe UI'")


@lru_cache(maxsize=64)
def icon(name: str, color: str = "#9b623c", size: int = 22) -> QIcon:
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.Antialiasing)
    p.scale(size / 24, size / 24)
    p.setPen(QPen(QColor(color), 1.65, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(Qt.NoBrush)

    def line(a, b, c, d):
        from PySide6.QtCore import QLineF

        p.drawLine(QLineF(a, b, c, d))

    if name in ("happy", "curious", "sleepy", "excited", "neutral"):
        p.drawEllipse(QRectF(2, 2, 20, 20))
        if name == "sleepy":
            line(6, 10, 9, 10)
            line(15, 10, 18, 10)
            line(9, 16, 15, 16)
        else:
            line(7, 9, 7, 10)
            line(17, 9, 17, 10)
            if name == "curious":
                line(6, 6, 9, 5)
                p.drawEllipse(QRectF(10, 14, 4, 4))
            elif name == "neutral":
                line(9, 16, 15, 16)
            else:
                smile = QPainterPath()
                smile.moveTo(7, 14)
                smile.quadTo(12, 20, 17, 14)
                p.drawPath(smile)
                if name == "excited":
                    line(4, 13, 6, 13)
                    line(18, 13, 20, 13)
    elif name == "ball":
        p.drawEllipse(QRectF(3, 3, 18, 18))
        path = QPainterPath()
        path.moveTo(6, 5)
        path.cubicTo(16, 6, 8, 18, 18, 19)
        p.drawPath(path)
    elif name == "frisbee":
        p.drawEllipse(QRectF(2, 7, 20, 10))
        p.drawEllipse(QRectF(6, 9, 12, 5))
        line(3, 5, 8, 5)
        line(1, 3, 5, 3)
    elif name == "light":
        p.drawEllipse(QRectF(8, 8, 8, 8))
        for coords in (
            (12, 2, 12, 5),
            (12, 19, 12, 22),
            (2, 12, 5, 12),
            (19, 12, 22, 12),
            (5, 5, 7, 7),
            (17, 17, 19, 19),
            (5, 19, 7, 17),
            (17, 7, 19, 5),
        ):
            line(*coords)
    elif name == "gomoku":
        for offset in (5, 12, 19):
            line(3, offset, 21, offset)
            line(offset, 3, offset, 21)
        p.setBrush(QColor(color))
        p.drawEllipse(QRectF(8.5, 8.5, 7, 7))
        p.setBrush(QColor("#fffdf9"))
        p.drawEllipse(QRectF(15.5, 1.5, 7, 7))
    elif name == "snack":
        p.drawRoundedRect(QRectF(5, 5, 14, 15), 3, 3)
        p.drawEllipse(QRectF(5, 3, 14, 5))
        p.drawEllipse(QRectF(9, 11, 6, 6))
        line(11, 13, 11, 13)
        line(14, 15, 14, 15)
    elif name in ("paw", "pet"):
        p.drawEllipse(QRectF(6, 13, 12, 8))
        for r in ((3, 8, 4, 6), (8, 3, 4, 6), (14, 3, 4, 6), (18, 8, 4, 6)):
            p.drawEllipse(QRectF(*r))
    elif name == "chat":
        path = QPainterPath()
        path.moveTo(5, 4)
        path.lineTo(19, 4)
        path.quadTo(21, 4, 21, 6)
        path.lineTo(21, 15)
        path.quadTo(21, 17, 19, 17)
        path.lineTo(10, 17)
        path.lineTo(5, 21)
        path.lineTo(5, 17)
        path.quadTo(3, 17, 3, 15)
        path.lineTo(3, 6)
        path.quadTo(3, 4, 5, 4)
        p.drawPath(path)
        line(7, 9, 17, 9)
        line(7, 12, 14, 12)
    elif name == "feed":
        p.drawEllipse(QRectF(2, 4, 6, 6))
        p.drawEllipse(QRectF(16, 14, 6, 6))
        line(7, 5, 20, 14)
        line(4, 9, 17, 19)
    elif name == "sleep":
        path = QPainterPath()
        path.moveTo(16, 3)
        path.cubicTo(3, 2, 1, 18, 13, 21)
        path.cubicTo(18, 22, 22, 17, 21, 13)
        path.cubicTo(12, 17, 8, 8, 16, 3)
        p.drawPath(path)
    elif name == "play":
        path = QPainterPath()
        path.moveTo(12, 2)
        path.lineTo(15, 9)
        path.lineTo(22, 12)
        path.lineTo(15, 15)
        path.lineTo(12, 22)
        path.lineTo(9, 15)
        path.lineTo(2, 12)
        path.lineTo(9, 9)
        path.closeSubpath()
        p.drawPath(path)
    elif name in ("show", "hide"):
        path = QPainterPath()
        path.moveTo(2, 12)
        path.quadTo(12, 1, 22, 12)
        path.quadTo(12, 23, 2, 12)
        p.drawPath(path)
        p.drawEllipse(QRectF(9, 9, 6, 6))
        if name == "hide":
            line(3, 3, 21, 21)
    elif name == "pause":
        p.drawRoundedRect(QRectF(6, 4, 4, 16), 1, 1)
        p.drawRoundedRect(QRectF(14, 4, 4, 16), 1, 1)
    elif name == "resume":
        path = QPainterPath()
        path.moveTo(7, 3)
        path.lineTo(21, 12)
        path.lineTo(7, 21)
        path.closeSubpath()
        p.drawPath(path)
    elif name in ("lock", "unlock"):
        p.drawRoundedRect(QRectF(5, 10, 14, 11), 2, 2)
        path = QPainterPath()
        path.moveTo(8, 10)
        path.lineTo(8, 7)
        path.cubicTo(8, 1, 16, 1, 16, 7)
        if name == "lock":
            path.lineTo(16, 10)
        p.drawPath(path)
        line(12, 14, 12, 17)
    elif name in ("window", "home"):
        p.drawRoundedRect(QRectF(2, 4, 20, 16), 2, 2)
        line(2, 9, 22, 9)
        if name == "home":
            line(8, 16, 16, 16)
    elif name == "settings":
        for y, knob in ((5, 8), (12, 16), (19, 10)):
            line(3, y, knob - 2, y)
            line(knob + 2, y, 21, y)
            p.drawEllipse(QRectF(knob - 2, y - 2, 4, 4))
    elif name == "stop":
        p.drawRoundedRect(QRectF(5, 5, 14, 14), 2, 2)
    elif name == "quit":
        line(12, 2, 12, 11)
        p.drawArc(QRectF(3, 3, 18, 18), 135 * 16, 270 * 16)
    elif name == "send":
        path = QPainterPath()
        path.moveTo(3, 3)
        path.lineTo(22, 12)
        path.lineTo(3, 21)
        path.lineTo(6, 12)
        path.closeSubpath()
        p.drawPath(path)
        line(6, 12, 15, 12)
    p.end()
    return QIcon(pixmap)


def avatar(size: int = 48) -> QPixmap:
    canvas = QPixmap(size * 2, size * 2)
    canvas.setDevicePixelRatio(2)
    canvas.fill(Qt.GlobalColor.transparent)
    p = QPainter(canvas)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#f2e3ce"))
    p.drawEllipse(QRectF(0, 0, size, size))
    clip = QPainterPath()
    clip.addEllipse(QRectF(0, 0, size, size))
    p.setClipPath(clip)
    image = QPixmap(str(asset_path("corgi-peek.png")))
    p.drawPixmap(
        QRectF(size * 0.09, size * 0.10, size * 0.82, size * 0.82), image, QRectF(image.rect())
    )
    p.end()
    return canvas


def label(text: str, name: str = "Muted") -> QLabel:
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setObjectName(name)
    return widget


def card() -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("Card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(18, 16, 18, 16)
    layout.setSpacing(12)
    return frame, layout


def add_action(menu, title, symbol, callback=None):
    action = menu.addAction(icon(symbol), title)
    action.setIconVisibleInMenu(True)
    if callback is not None:
        action.triggered.connect(lambda checked=False: callback())
    return action
