"""Local vector effects, independent of the pet window and its states."""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap

COLORS = {
    "heart": "#ed718b",
    "note": "#8b82ca",
    "anger": "#ed6b55",
    "star": "#ffc64d",
    "sparkle": "#ffe09a",
    "exclaim": "#eab448",
    "question": "#6fadd4",
    "snot": "#a7d9e8",
    "dust": "#ac9e90",
    "crumb": "#c88a4d",
    "ring": "#c5af97",
}


def symbol_path(kind: str) -> QPainterPath:
    """Construct shapes in a normalized -1..1 square, without font glyphs."""
    path = QPainterPath()
    if kind == "heart":
        path.moveTo(0, 0.9)
        path.cubicTo(-1.7, -0.05, -0.85, -1.25, 0, -0.48)
        path.cubicTo(0.85, -1.25, 1.7, -0.05, 0, 0.9)
    elif kind in {"star", "sparkle"}:
        points = 5 if kind == "star" else 4
        for i in range(points * 2):
            angle = -math.pi / 2 + i * math.pi / points
            radius = 0.95 if i % 2 == 0 else (0.43 if points == 5 else 0.25)
            x, y = math.cos(angle) * radius, math.sin(angle) * radius
            path.moveTo(x, y) if i == 0 else path.lineTo(x, y)
        path.closeSubpath()
    elif kind == "anger":
        # Four bent strokes form a comic anger vein, with an open center.
        stroke = QPainterPath()
        stroke.moveTo(-0.8, -0.8)
        stroke.lineTo(-0.45, -0.8)
        stroke.quadTo(-0.22, -0.8, -0.22, -0.22)
        from PySide6.QtGui import QPainterPathStroker, QTransform

        outline = QPainterPathStroker()
        outline.setWidth(0.18)
        outline.setCapStyle(Qt.PenCapStyle.RoundCap)
        for angle in (0, 90, 180, 270):
            transform = QTransform().rotate(angle)
            path.addPath(transform.map(outline.createStroke(stroke)))
    elif kind == "note":
        path.addEllipse(QRectF(-0.92, 0.25, 0.57, 0.4))
        path.addEllipse(QRectF(0.21, 0.05, 0.57, 0.4))
        path.addRect(QRectF(-0.47, -0.65, 0.13, 1.08))
        path.addRect(QRectF(0.65, -0.85, 0.13, 1.08))
        path.moveTo(-0.47, -0.65)
        path.lineTo(0.78, -0.85)
        path.lineTo(0.78, -0.57)
        path.lineTo(-0.47, -0.37)
        path.closeSubpath()
    elif kind == "exclaim":
        path.addRoundedRect(QRectF(-0.16, -0.85, 0.32, 1.15), 0.12, 0.12)
        path.addEllipse(QRectF(-0.18, 0.55, 0.36, 0.36))
    elif kind == "question":
        from PySide6.QtGui import QPainterPathStroker

        curve = QPainterPath()
        curve.moveTo(-0.48, -0.5)
        curve.cubicTo(-0.48, -1.05, 0.55, -1.05, 0.55, -0.45)
        curve.cubicTo(0.55, -0.08, 0, -0.1, 0, 0.32)
        stroke = QPainterPathStroker()
        stroke.setWidth(0.25)
        stroke.setCapStyle(Qt.PenCapStyle.RoundCap)
        path.addPath(stroke.createStroke(curve))
        path.addEllipse(QRectF(-0.16, 0.59, 0.32, 0.32))
    elif kind == "snot":
        path.addEllipse(QRectF(-0.76, -0.88, 1.52, 1.68))
    elif kind in {"dust", "ring"}:
        path.addEllipse(QRectF(-0.85, -0.85, 1.7, 1.7))
    elif kind == "crumb":
        path.moveTo(-0.75, -0.55)
        path.lineTo(0.45, -0.8)
        path.lineTo(0.85, 0.28)
        path.lineTo(-0.25, 0.8)
        path.closeSubpath()
    else:
        raise ValueError(f"Unknown effect shape: {kind}")
    return path


@lru_cache(maxsize=256)
def symbol_pixmap(kind: str, pixels: int, dpr: float = 1.0) -> QPixmap:
    """Cache vector rasterization at the requested logical pixel size."""
    pixels = max(4, pixels)
    pixmap = QPixmap(round(pixels * dpr), round(pixels * dpr))
    pixmap.setDevicePixelRatio(dpr)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.translate(pixels / 2, pixels / 2)
    painter.scale(pixels / 2.2, pixels / 2.2)
    color = QColor(COLORS[kind])
    if kind == "snot":
        color.setAlpha(145)
        painter.setPen(QPen(QColor("#7eb7ca"), 0.065))
    elif kind == "ring":
        painter.setPen(QPen(color, 0.12))
    else:
        painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(Qt.BrushStyle.NoBrush if kind == "ring" else color)
    painter.drawPath(symbol_path(kind))
    if kind == "snot":
        highlight = QPainterPath()
        highlight.moveTo(-0.43, -0.15)
        highlight.quadTo(-0.43, -0.55, -0.12, -0.6)
        painter.setPen(
            QPen(QColor("#ffffff"), 0.12, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        )
        painter.drawPath(highlight)
    painter.end()
    return pixmap


@dataclass
class Particle:
    kind: str
    x: float
    y: float
    vx: float = 0.0
    vy: float = 0.0
    angle: float = 0.0
    angular_velocity: float = 0.0
    lifetime: float = 1.0
    age: float = 0.0
    gravity: float = 0.0
    damp: float = 0.0
    size: float = 8.0
    fade: str = "soft"

    @property
    def progress(self) -> float:
        return min(1.0, self.age / max(self.lifetime, 0.001))

    @property
    def opacity(self) -> float:
        remaining = 1 - self.progress
        return remaining if self.fade == "linear" else remaining * remaining


class ParticleSystem:
    LIMIT = 80

    def __init__(self) -> None:
        self.particles: list[Particle] = []

    def spawn(self, kind: str, x: float, y: float, **params) -> Particle:
        if kind not in COLORS:
            raise ValueError(f"Unknown particle: {kind}")
        particle = Particle(kind, x, y, **params)
        self.particles.append(particle)
        if len(self.particles) > self.LIMIT:
            del self.particles[: len(self.particles) - self.LIMIT]
        return particle

    def update(self, dt: float) -> None:
        dt = max(0, dt)
        for particle in self.particles:
            particle.age += dt
            if particle.kind != "ring":
                damping = max(0, 1 - particle.damp * dt)
                particle.vx *= damping
                particle.vy = particle.vy * damping + particle.gravity * dt
                particle.x += particle.vx * dt
                particle.y += particle.vy * dt
            particle.angle += particle.angular_velocity * dt
        self.particles[:] = [p for p in self.particles if p.age < p.lifetime]

    def paint(self, painter: QPainter) -> None:
        for particle in self.particles:
            painter.save()
            painter.setOpacity(particle.opacity * (0.55 if particle.kind == "dust" else 1))
            painter.translate(particle.x, particle.y)
            painter.rotate(particle.angle)
            if particle.kind == "ring":
                expansion = 1 + 2.5 * particle.progress
                painter.scale(expansion, expansion)
            size = max(4, round(particle.size))
            pixmap = symbol_pixmap(
                particle.kind, size, round(painter.device().devicePixelRatioF(), 2)
            )
            painter.drawPixmap(-size // 2, -size // 2, pixmap)
            painter.restore()

    def clear(self) -> None:
        self.particles.clear()


@dataclass
class EmotionMark:
    kind: str
    started: float
    lifetime: float | None = 1.4
    ending: float | None = None

    def stop(self, now: float) -> None:
        if self.ending is None:
            self.ending = now

    def appearance(self, now: float) -> tuple[float, float, float]:
        """Return scale, opacity and exit lift (in normalized mark units)."""
        elapsed = max(0, now - self.started)
        p = min(1, elapsed / 0.3)
        # Two smooth segments: 0.6 → 1.08 → 1.0.
        if p < 0.65:
            scale = 0.6 + 0.48 * math.sin(p / 0.65 * math.pi / 2)
        else:
            scale = 1 + 0.08 * (1 + math.cos((p - 0.65) / 0.35 * math.pi)) / 2
        end = self.ending
        if self.lifetime is not None:
            natural_end = self.started + self.lifetime
            end = natural_end if end is None else min(end, natural_end)
        fade = 0 if end is None else max(0, min(1, (now - end) / 0.2))
        if self.kind == "snot":
            scale *= 1 + 0.09 * math.sin(elapsed * 2)
        return scale, 1 - fade, fade * 0.4

    def alive(self, now: float) -> bool:
        return self.appearance(now)[1] > 0
