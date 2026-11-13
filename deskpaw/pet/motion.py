"""Pose transition value objects and interpolation."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QPixmap


@dataclass(frozen=True)
class PoseTransition:
    previous: QPixmap
    started: float
    duration: float
    style: str
    motion: BodyMotion | None = None
    snapshot: bool = False


@dataclass(frozen=True)
class BodyMotion:
    tilt: float = 0.0
    y_offset: float = 0.0
    x_scale: float = 1.0
    y_scale: float = 1.0

    def toward(self, other: BodyMotion, amount: float) -> BodyMotion:
        return BodyMotion(
            *(
                start + (end - start) * amount
                for start, end in zip(
                    (self.tilt, self.y_offset, self.x_scale, self.y_scale),
                    (other.tilt, other.y_offset, other.x_scale, other.y_scale),
                )
            )
        )


def smoothstep(value: float) -> float:
    value = max(0.0, min(1.0, value))
    return value * value * (3 - 2 * value)
