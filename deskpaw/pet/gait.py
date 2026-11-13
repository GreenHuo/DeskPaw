"""Short, grounded walking cycle made from the original corgi artwork."""

from __future__ import annotations

import math
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import (
    QColor,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPixmap,
    QPolygonF,
)


@dataclass(frozen=True)
class Leg:
    name: str
    outline: tuple[tuple[int, int], ...]
    hip: tuple[int, int]
    paw: tuple[int, int]
    offset: float


# Coordinates are on the supplied 1374 × 1145 reference. Lower legs are
# isolated so the head and torso remain on exactly the same pixels each frame.
LEGS = (
    Leg(
        "far_front",
        ((240, 925), (375, 865), (445, 915), (445, 1145), (200, 1145), (195, 990)),
        (330, 910),
        (320, 1070),
        0.5,
    ),
    Leg(
        "near_front",
        ((450, 925), (570, 865), (670, 925), (650, 1145), (425, 1145), (425, 990)),
        (535, 910),
        (520, 1100),
        0.0,
    ),
    Leg(
        "far_hind",
        ((885, 900), (1010, 850), (1075, 905), (1075, 1145), (810, 1145), (830, 975)),
        (965, 905),
        (945, 1030),
        0.0,
    ),
    Leg(
        "near_hind",
        ((1130, 905), (1275, 850), (1374, 905), (1374, 1145), (1080, 1145), (1100, 975)),
        (1190, 910),
        (1215, 1080),
        0.5,
    ),
)


def foot_motion(leg: Leg, phase: float) -> tuple[float, float, float, float, float]:
    """Return translation, rotation and paw coordinates for one stride phase.

    The stance half sweeps the paw backwards along the ground. During swing it
    travels forwards with at most 14 source pixels of lift (about 1–4 screen
    pixels across the supported scale range). Rotation is compensated at the paw.
    """
    angle = 2 * math.pi * (phase + leg.offset)
    stride = math.cos(angle)
    radians = math.radians(-6 * stride)
    dx = 28 * stride
    paw_x, paw_y = leg.paw
    hip_x, hip_y = leg.hip
    rotated_y = math.sin(radians) * (paw_x - hip_x) + math.cos(radians) * (paw_y - hip_y)
    delta_y = rotated_y - (paw_y - hip_y)
    lift = 14 * max(0, math.sin(angle))
    dy = -delta_y - lift
    rotated_x = math.cos(radians) * (paw_x - hip_x) - math.sin(radians) * (paw_y - hip_y)
    return dx, dy, math.degrees(radians), hip_x + rotated_x + dx, paw_y - lift


def running_foot_motion(leg: Leg, phase: float) -> tuple[float, float, float, float, float]:
    """Bound with the hind pair pushing off before the front pair reaches out."""
    # The slight delay between near and far paws keeps each pair readable in
    # the small desktop sprite. The larger forward reach and lift distinguish
    # fetching from the grounded walk without changing the dog's upper body.
    offsets = {
        "far_hind": 0.04,
        "near_hind": -0.04,
        "far_front": 0.49,
        "near_front": 0.57,
    }
    angle = 2 * math.pi * (phase + offsets[leg.name])
    stride = math.cos(angle)
    radians = math.radians(-14 * stride)
    dx = 62 * stride
    paw_x, paw_y = leg.paw
    hip_x, hip_y = leg.hip
    rotated_y = math.sin(radians) * (paw_x - hip_x) + math.cos(radians) * (paw_y - hip_y)
    lift = 54 * max(0, math.sin(angle))
    dy = (paw_y - hip_y) - rotated_y - lift
    rotated_x = math.cos(radians) * (paw_x - hip_x) - math.sin(radians) * (paw_y - hip_y)
    return dx, dy, math.degrees(radians), hip_x + rotated_x + dx, paw_y - lift


class WalkingGait:
    FRAME_COUNT = 24
    motion = staticmethod(foot_motion)

    def __init__(self, source: QPixmap, size: QSize) -> None:
        if source.isNull():
            raise ValueError("Walking source image is empty")
        self.source = source
        self.size = size
        self.frames = self._render_frames()

    def frame_at(self, phase: float) -> QPixmap:
        return self.frames[int(phase * self.FRAME_COUNT) % self.FRAME_COUNT]

    def _render_frames(self) -> tuple[QPixmap, ...]:
        source = self.source
        ratio_x, ratio_y = source.width() / 1374, source.height() / 1145
        paths: list[QPainterPath] = []
        body = QPainterPath()
        body.addRect(QRectF(0, 0, source.width(), source.height()))
        for leg in LEGS:
            path = QPainterPath()
            path.addPolygon(QPolygonF([QPointF(x * ratio_x, y * ratio_y) for x, y in leg.outline]))
            path.closeSubpath()
            paths.append(path)
            body = body.subtracted(path)

        # Original upper fur overlaps the articulated lower legs with a soft
        # edge. It conceals the hip seam without leaving duplicate feet.
        upper = QPixmap(source.size())
        upper.fill(Qt.GlobalColor.transparent)
        painter = QPainter(upper)
        painter.drawPixmap(0, 0, source)
        painter.setCompositionMode(QPainter.CompositionMode_DestinationIn)
        gradient = QLinearGradient(0, 940 * ratio_y, 0, 980 * ratio_y)
        gradient.setColorAt(0, QColor(0, 0, 0, 255))
        gradient.setColorAt(1, QColor(0, 0, 0, 0))
        painter.fillRect(QRectF(0, 0, source.width(), source.height()), gradient)
        painter.end()

        frames = []
        for index in range(self.FRAME_COUNT):
            image = QImage(self.size, QImage.Format.Format_ARGB32_Premultiplied)
            image.fill(Qt.GlobalColor.transparent)
            painter = QPainter(image)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            painter.scale(self.size.width() / source.width(), self.size.height() / source.height())
            painter.save()
            painter.setClipPath(body)
            painter.drawPixmap(0, 0, source)
            painter.restore()
            for leg, path in zip(LEGS, paths):
                dx, dy, angle, _, _ = self.motion(leg, index / self.FRAME_COUNT)
                hip_x, hip_y = leg.hip
                hip_x *= ratio_x
                hip_y *= ratio_y
                painter.save()
                painter.translate(dx * ratio_x, dy * ratio_y)
                painter.translate(hip_x, hip_y)
                painter.rotate(angle)
                painter.translate(-hip_x, -hip_y)
                painter.setClipPath(path)
                painter.drawPixmap(0, 0, source)
                painter.restore()
            painter.drawPixmap(0, 0, upper)
            painter.end()
            frames.append(QPixmap.fromImage(image))
        return tuple(frames)


class RunningGait(WalkingGait):
    motion = staticmethod(running_foot_motion)
