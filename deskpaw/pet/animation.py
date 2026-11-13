"""Pet sprite sizing, pose transitions and frame rendering."""

from __future__ import annotations

import math
import random
import sys
import time

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QCursor,
    QFont,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
    QRegion,
)

from deskpaw.pet.effects import EmotionMark, symbol_pixmap
from deskpaw.pet.gait import RunningGait, WalkingGait

from .constants import EVENT_EFFECTS, STATE_EFFECTS
from .motion import BodyMotion, PoseTransition, smoothstep


class PetAnimationMixin:
    """Internal behavior of PetWindow; state and Qt lifetime belong to the window."""

    def _resize_pet(self) -> None:
        self._pose_transition = None
        ratio = self.settings.scale / 100
        self.pet_pixmap = self.original.scaled(
            round(320 * ratio),
            round(267 * ratio),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        bubble_height = max(36, round(52 * ratio))
        self.floor_padding = max(6, round(10 * ratio))
        self.normal_height = (
            self.pet_pixmap.height() + bubble_height + 20 + max(32, round(48 * ratio))
        )
        self.resize(
            max(180, round(360 * ratio), self.pet_pixmap.width() + 40),
            self.normal_height,
        )
        self.pet_x = (self.width() - self.pet_pixmap.width()) // 2
        self.pet_y = self.normal_height - self.pet_pixmap.height() - self.floor_padding
        if hasattr(self, "particles"):
            self.particles.clear()
        self.sleep_pixmap = self.sleep_image.scaled(
            self.pet_pixmap.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.peek_pixmap = self.peek_image.scaled(
            round(210 * ratio),
            round(210 * ratio),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.back_pixmap = self.back_image.scaled(
            self.pet_pixmap.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.lift_pixmap = self.lift_image.scaled(
            self.pet_pixmap.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.lift_b_pixmap = self.lift_b_image.scaled(
            self.pet_pixmap.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.paw_pixmap = self.paw_image.scaled(
            self.pet_pixmap.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.happy_pixmap = self.happy_image.scaled(
            self.pet_pixmap.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.walk_gait = WalkingGait(self.original, self.pet_pixmap.size())
        self.run_gait = RunningGait(self.run_original, self.pet_pixmap.size())
        # Opposite contacts also give tests a stable handle on the cycle.
        self.walk_a_pixmap = self.walk_gait.frame_at(0)
        self.walk_b_pixmap = self.walk_gait.frame_at(0.5)
        self.yawn_pixmap = self.yawn_image.scaled(
            self.pet_pixmap.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        for name in ("sit", "sit_blink", "sit_look", "sit_scratch"):
            image = getattr(self, f"{name}_image")
            setattr(
                self,
                f"{name}_pixmap",
                image.scaled(
                    self.pet_pixmap.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                ),
            )
        self.pose_bounds = {}
        for name, value in vars(self).items():
            if name.endswith("_pixmap") and isinstance(value, QPixmap) and not value.isNull():
                self.pose_bounds[value.cacheKey()] = QRegion(value.mask()).boundingRect()
        for frame in (*self.walk_gait.frames, *self.run_gait.frames):
            self.pose_bounds[frame.cacheKey()] = QRegion(frame.mask()).boundingRect()
        self.pose_families = {}
        for family, pixmaps in (
            (
                "sit",
                (
                    self.sit_pixmap,
                    self.sit_blink_pixmap,
                    self.sit_look_pixmap,
                    self.sit_scratch_pixmap,
                ),
            ),
            ("stand", (self.pet_pixmap, self.paw_pixmap, self.happy_pixmap, self.yawn_pixmap)),
            ("air", (self.lift_pixmap, self.lift_b_pixmap)),
            ("peek", (self.peek_pixmap,)),
            ("walk", self.walk_gait.frames),
            ("run", self.run_gait.frames),
        ):
            for pixmap in pixmaps:
                if not pixmap.isNull():
                    self.pose_families[pixmap.cacheKey()] = family
        if self.perch is not None:
            # Only the head and front paws peek over the title bar;
            # normal chat bubbles are omitted while perched.
            bounds = self.pose_bounds[self.peek_pixmap.cacheKey()]
            self.perch_overlap = max(3, round(bounds.height() * 0.1))
            self.normal_height = bounds.height() + self.floor_padding + 12
            self.pet_y = self.normal_height - self.pet_pixmap.height() - self.floor_padding
            self.resize(max(72, bounds.width() + 24), self.normal_height)
            self.pet_x = (self.width() - self.pet_pixmap.width()) // 2
        self._update_mask()

    def _active_pixmap(self) -> QPixmap:
        if self.perch is not None or self.state == "perch":
            return self.peek_pixmap
        if self.state == "idle" and time.monotonic() < self.roam_until:
            candidate = self._walk_pixmap()
            if not candidate.isNull():
                return candidate
        if self.state == "idle_blink" and not self.sit_blink_pixmap.isNull():
            return self.sit_blink_pixmap
        if self.state in {"idle_glance", "look"} and not self.sit_look_pixmap.isNull():
            return self.sit_look_pixmap
        if self.state == "idle_scratch" and not self.sit_scratch_pixmap.isNull():
            return self.sit_scratch_pixmap
        if self.state == "idle" and not self.sit_pixmap.isNull():
            return self.sit_pixmap
        if self.state in {"lie", "sleep"} and not self.sleep_pixmap.isNull():
            return self.sleep_pixmap
        if self.state == "yawn" and not self.yawn_pixmap.isNull():
            return self.yawn_pixmap
        if self.state == "annoyed" and not self.back_pixmap.isNull():
            return self.back_pixmap
        if self.state == "drag" and not self.lift_b_pixmap.isNull():
            swing = int((time.monotonic() - self.state_since) / 0.18) % 2
            return self.lift_pixmap if swing == 0 else self.lift_b_pixmap
        if self.state in {"drop", "tumble"} and not self.lift_pixmap.isNull():
            return self.lift_pixmap
        if self.state in {"paw", "handshake_offer"} and not self.paw_pixmap.isNull():
            return self.paw_pixmap
        if self.state == "handshake" and not self.paw_pixmap.isNull():
            shake = int((time.monotonic() - self.state_since) / 0.16) % 2
            return self.paw_pixmap if shake == 0 else self.pet_pixmap
        if self.state in {"happy", "play"} and not self.happy_pixmap.isNull():
            return self.happy_pixmap
        if self.state == "fetch":
            return self._run_pixmap()
        return self.pet_pixmap

    def _walk_phase(self) -> float:
        # Advance feet with actual travel, so a stopped pet cannot step in place.
        return self.walk_distance / max(8, 28 * self.settings.scale / 100)

    def _walk_pixmap(self) -> QPixmap:
        return self.walk_gait.frame_at(self._walk_phase() / 2)

    def _run_phase(self) -> float:
        return self.walk_distance / max(14, 56 * self.settings.scale / 100)

    def _run_pixmap(self) -> QPixmap:
        return self.run_gait.frame_at(self._run_phase())

    def _travel_facing_scale(self) -> int:
        # Both motion sources face image-left; mirror them only for rightward travel.
        return -self.direction

    def _update_mask(self) -> None:
        if sys.platform == "darwin":
            # macOS can leave the previous shaped-window region behind during
            # rapid pose changes. A clear alpha buffer gives the same appearance.
            self.clearMask()
            return
        # The native mask lets clicks in transparent corners reach the desktop.
        # Allow transformed feet, symbols and particles to remain visible on
        # Windows. Leave the large gap above a dragged pet's ground transparent.
        mask = QRegion(0, 0, self.width(), self.normal_height)
        mask = mask.united(QRegion(self._shadow_geometry()[0].toRect(), QRegion.RegionType.Ellipse))
        if self.state == "sleep" or (self.bubble and time.monotonic() < self.bubble_until):
            mask = mask.united(QRegion(self._bubble_rect().toRect()))
        self.setMask(mask)

    def _transition_source(self, now: float) -> tuple[QPixmap, BodyMotion, bool]:
        motion = self._body_motion(now)
        interrupted = (
            self._pose_transition is not None
            and now < self._pose_transition.started + self._pose_transition.duration
        )
        return (
            self._pose_snapshot(now) if interrupted else self._active_pixmap(),
            motion,
            interrupted,
        )

    def _begin_pose_transition(
        self,
        previous: QPixmap,
        previous_motion: BodyMotion | None = None,
        *,
        snapshot: bool = False,
        started: float | None = None,
    ) -> None:
        started = time.monotonic() if started is None else started
        old_transition = self._pose_transition
        if old_transition is not None and old_transition.snapshot:
            self.pose_bounds.pop(old_transition.previous.cacheKey(), None)
        current = self._active_pixmap()
        if not snapshot and previous.cacheKey() == current.cacheKey():
            target = self._target_body_motion(started)
            if previous_motion is None or all(
                abs(a - b) < 0.001
                for a, b in zip(
                    (
                        previous_motion.tilt,
                        previous_motion.y_offset,
                        previous_motion.x_scale,
                        previous_motion.y_scale,
                    ),
                    (target.tilt, target.y_offset, target.x_scale, target.y_scale),
                )
            ):
                self._pose_transition = None
            else:
                self._pose_transition = PoseTransition(
                    previous, started, 0.16, "motion", previous_motion
                )
            return
        old_family = None if snapshot else self.pose_families.get(previous.cacheKey())
        new_family = self.pose_families.get(current.cacheKey())
        style = (
            "fade"
            if snapshot or (old_family == new_family and old_family in {"sit", "stand", "air"})
            else "bridge"
        )
        duration = 0.12 if snapshot else 0.09 if style == "fade" else 0.20
        self._pose_transition = PoseTransition(
            previous, started, duration, style, previous_motion, snapshot
        )
        if snapshot:
            self.pose_bounds[previous.cacheKey()] = QRegion(previous.mask()).boundingRect()

    def _pose_layers(
        self, current: QPixmap, now: float
    ) -> tuple[tuple[QPixmap, float, float, float], ...]:
        """Choose aligned sprite layers for a pose transition."""
        transition = self._pose_transition
        if transition is None:
            return self._loop_layers(current, now)
        progress = max(0.0, (now - transition.started) / transition.duration)
        if progress >= 1.0:
            self._pose_transition = None
            if transition.snapshot:
                self.pose_bounds.pop(transition.previous.cacheKey(), None)
            return self._loop_layers(current, now)
        if transition.style == "motion":
            return ((current, 1.0, 1.0, 1.0),)
        previous = transition.previous
        if transition.style == "fade":
            blend = smoothstep(progress)
            return ((previous, 1.0, 1.0, 1.0 - blend), (current, 1.0, 1.0, blend))
        old_width = max(1, self.pose_bounds[previous.cacheKey()].width())
        new_width = max(1, self.pose_bounds[current.cacheKey()].width())
        bridge_width = min(old_width, new_width) * 0.82
        if progress < 0.48:
            amount = smoothstep(progress / 0.48)
            midpoint_x = max(0.55, bridge_width / old_width)
            return ((previous, 1 + (midpoint_x - 1) * amount, 1 - 0.10 * amount, 1.0),)
        if progress < 0.52:
            blend = smoothstep((progress - 0.48) / 0.04)
            return (
                (previous, max(0.55, bridge_width / old_width), 0.90, 1 - blend),
                (current, max(0.55, bridge_width / new_width), 0.90, blend),
            )
        amount = smoothstep((progress - 0.52) / 0.48)
        midpoint_x = max(0.55, bridge_width / new_width)
        return ((current, midpoint_x + (1 - midpoint_x) * amount, 0.90 + 0.10 * amount, 1.0),)

    def _loop_layers(
        self, current: QPixmap, now: float
    ) -> tuple[tuple[QPixmap, float, float, float], ...]:
        if self.state == "drag":
            pair, period = (self.lift_pixmap, self.lift_b_pixmap), 0.18
        elif self.state == "handshake":
            pair, period = (self.paw_pixmap, self.pet_pixmap), 0.16
        else:
            return ((current, 1.0, 1.0, 1.0),)
        if pair[0].isNull() or pair[1].isNull():
            return ((current, 1.0, 1.0, 1.0),)
        fraction = (max(0.0, now - self.state_since) / period) % 1.0
        blend = smoothstep((fraction - 0.55) / 0.45)
        if blend <= 0:
            return ((current, 1.0, 1.0, 1.0),)
        next_pose = pair[1] if current.cacheKey() == pair[0].cacheKey() else pair[0]
        return ((current, 1.0, 1.0, 1.0 - blend), (next_pose, 1.0, 1.0, blend))

    def set_effects_enabled(self, enabled: bool) -> None:
        self.settings.effects = enabled
        if not enabled:
            self.particles.clear()
            self.emotion = None
        elif self.state in {"sleep", "dizzy"}:
            kind, lifetime = STATE_EFFECTS[self.state]["mark"]
            self.emotion = EmotionMark(kind, time.monotonic(), lifetime)
        self.update()

    def _emit_specs(self, specs) -> None:
        if not self.settings.effects:
            return
        ratio = self.settings.scale / 100
        for kind, count, anchor in specs:
            x = self.pet_x + self.pet_pixmap.width() * (0.3 if anchor == "mouth" else 0.5)
            y = self.pet_y + self.pet_pixmap.height() * (0.5 if anchor == "mouth" else 0.18)
            if anchor == "feet":
                y = self.normal_height - self.floor_padding - 2
            for i in range(count):
                if kind == "dust":
                    side = -1 if i % 2 == 0 else 1
                    params = dict(
                        vx=side * random.uniform(24, 65) * ratio,
                        vy=-random.uniform(8, 22) * ratio,
                        gravity=40 * ratio,
                        damp=1.5,
                        size=random.uniform(10, 17) * ratio,
                        lifetime=random.uniform(0.45, 0.7),
                    )
                elif kind == "crumb":
                    params = dict(
                        vx=random.uniform(-35, 35) * ratio,
                        vy=-random.uniform(12, 30) * ratio,
                        gravity=100 * ratio,
                        damp=0.3,
                        size=random.uniform(5, 9) * ratio,
                        angular_velocity=random.uniform(-180, 180),
                        lifetime=0.65,
                    )
                else:
                    params = dict(
                        vx=random.uniform(-25, 25) * ratio,
                        vy=-random.uniform(22, 45) * ratio,
                        damp=0.4,
                        size=random.uniform(16, 23) * ratio,
                        lifetime=1.15,
                        angular_velocity=random.uniform(-35, 35),
                        fade="linear",
                    )
                self.particles.spawn(kind, x + random.uniform(-14, 14) * ratio, y, **params)

    def _effect_event(self, name: str) -> None:
        spec = EVENT_EFFECTS[name]
        if "squash" in spec:
            strength, duration, axis = spec["squash"]
            self._squash = (time.monotonic(), strength, duration, axis)
        self._emit_specs(spec.get("particles", ()))

    def _landing_impact(self, strength: float = 1) -> None:
        self._effect_event(STATE_EFFECTS["tumble" if strength > 1 else "drop"]["landing"])

    def _squash_scale(self, now: float) -> tuple[float, float]:
        if self._squash is None:
            return 1, 1
        started, strength, duration, axis = self._squash
        progress = max(0, (now - started) / duration)
        if progress >= 1:
            self._squash = None
            return 1, 1
        wave = strength * (1 - progress) ** 2 * math.cos(2 * math.pi * progress)
        return (1 + wave, 1 - wave * 0.5) if axis == "x" else (1 + wave * 0.5, 1 - wave)

    def _state_deformation(self, elapsed: float) -> tuple[float, float]:
        name = STATE_EFFECTS.get(self.state, {}).get("deform")
        if name == "bounce":
            if elapsed < 0.12:
                return 1.03, 0.94
            if elapsed < 0.55:
                stretch = 0.08 * math.sin(math.pi * (elapsed - 0.12) / 0.43)
                return 1 - stretch * 0.5, 1 + stretch
        elif name == "eat":
            compress = 0.03 * max(0, math.sin(elapsed * 10))
            return 1 - compress, 1 + compress * 0.5
        return 1, 1

    def _shadow_geometry(self, y_offset: float = 0) -> tuple[QRectF, float]:
        height = max(0, self._floor_y() - self.y()) + max(0, -y_offset)
        p = min(1, height / max(1, self.pet_pixmap.height()))
        scale, opacity = 1 - 0.55 * p, 0.23 * (1 - 0.75 * p)
        width = self.pet_pixmap.width() * 0.63 * scale
        thickness = max(4, 11 * self.settings.scale / 100) * scale
        if self.state in {"lie", "sleep", "perch"}:
            width *= 1.14
            thickness *= 0.7
        center = self.pet_x + self.pet_pixmap.width() / 2
        ground = self.normal_height - self.floor_padding + max(0, self._floor_y() - self.y())
        return QRectF(center - width / 2, ground - thickness / 2, width, thickness), opacity

    def _draw_shadow(self, painter: QPainter, y_offset: float) -> None:
        if self.perch is not None:
            # Contact shadows under the two paws instead of a full-body floor shadow.
            width = self.pose_bounds[self.peek_pixmap.cacheKey()].width()
            edge = self.normal_height - self.floor_padding - self.perch_overlap
            painter.save()
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(68, 49, 35, 35))
            for offset in (-0.31, 0.31):
                painter.drawEllipse(
                    QRectF(
                        self.width() / 2 + width * offset - width * 0.09, edge - 1, width * 0.18, 3
                    )
                )
            painter.restore()
            return
        rect, opacity = self._shadow_geometry(y_offset)
        painter.save()
        painter.translate(rect.center())
        painter.scale(rect.width() / 2, rect.height() / 2)
        gradient = QRadialGradient(0, 0, 1)
        gradient.setColorAt(0, QColor(68, 49, 35, round(255 * opacity)))
        gradient.setColorAt(1, QColor(68, 49, 35, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradient)
        painter.drawEllipse(QRectF(-1, -1, 2, 2))
        painter.restore()

    def _draw_emotion(self, painter: QPainter, now: float) -> None:
        if not self.settings.effects or self.emotion is None:
            return
        mark = self.emotion
        scale, opacity, lift = mark.appearance(now)
        if opacity <= 0:
            return
        ratio = self.settings.scale / 100
        size = max(18, round(28 * ratio))
        x = self.pet_x + self.pet_pixmap.width() * 0.38
        lower_bound = 0 if self.perch else self._bubble_rect().bottom() + 12
        if self.perch:
            size, y = 12, 9
        else:
            y = self.pet_y - size * 0.65
        if mark.kind == "snot":
            pixmap = self._active_pixmap()
            bounds = self.pose_bounds[pixmap.cacheKey()]
            center_x, center_y = self._pose_center(pixmap, 1, 1)
            x = center_x - pixmap.width() / 2 + bounds.left() + bounds.width() * 0.14
            y = center_y - pixmap.height() / 2 + bounds.top() + bounds.height() * 0.70
        elif mark.kind == "star":
            phase = (now - mark.started) * 6
            x += math.cos(phase) * 18 * ratio
            y += math.sin(phase) * 4 * ratio
        if y - size * 0.6 < lower_bound:
            return  # Bubble priority when the available headroom is too small.
        painter.save()
        painter.setOpacity(opacity)
        painter.translate(x, y - lift * size)
        painter.scale(scale, scale)
        pixmap = symbol_pixmap(mark.kind, size, round(painter.device().devicePixelRatioF(), 2))
        painter.drawPixmap(-size // 2, -size // 2, pixmap)
        painter.restore()

    def _pose_center(self, pixmap: QPixmap, x_scale: float, y_scale: float) -> tuple[float, float]:
        # Different generated canvases have different transparent margins.
        # Anchor the visible feet, rather than the PNG rectangle, to the floor.
        bounds = self.pose_bounds[pixmap.cacheKey()]
        x = self.pet_x + self.pet_pixmap.width() / 2
        x -= (bounds.center().x() + 0.5 - pixmap.width() / 2) * x_scale
        y = self.normal_height - self.floor_padding
        y -= (bounds.bottom() + 1 - pixmap.height() / 2) * y_scale
        return x, y

    def _bubble_rect(self) -> QRectF:
        ratio = self.settings.scale / 100
        width = max(150, round(270 * ratio))
        height = max(36, round(52 * ratio))
        # Generated poses have different transparent margins and visible
        # heights. Keep the bubble near the visible ears, not the PNG canvas.
        pixmap = self._active_pixmap()
        visible_height = self.pose_bounds[pixmap.cacheKey()].height()
        transition = self._pose_transition
        if transition is not None and time.monotonic() < transition.started + transition.duration:
            visible_height = max(
                visible_height, self.pose_bounds[transition.previous.cacheKey()].height()
            )
        if self.state in {"lie", "sleep"}:
            visible_height *= 1.01  # Leave room for the breathing animation.
        pet_top = self.normal_height - self.floor_padding - visible_height
        gap = 10 + max(6, round(8 * ratio))  # Tail plus a small gap above the ears.
        top = max(2, pet_top - gap - height)
        return QRectF((self.width() - width) / 2, top, width, height)

    def _target_body_motion(self, now: float) -> BodyMotion:
        elapsed = now - self.state_since
        tilt = 0.0
        y_offset = 0.0
        x_scale = 1.0
        y_scale = 1.0
        if self.state == "idle":
            y_scale = 1 + 0.006 * math.sin(now * 2.7)
            if now < self.roam_until:
                y_offset = (
                    -1.2 * self.settings.scale / 100 * abs(math.sin(self._walk_phase() * math.pi))
                )
                x_scale = self._travel_facing_scale()
        elif self.state == "fetch":
            bound = max(0, math.sin(2 * math.pi * self._run_phase()))
            y_offset = -14 * self.settings.scale / 100 * bound
            tilt = 2.5 * math.sin(2 * math.pi * self._run_phase()) * self.direction
            y_scale = 1 + 0.018 * bound
            x_scale = self._travel_facing_scale()
        elif self.state == "look":
            pointer = QCursor.pos()
            dx = pointer.x() - (self.x() + self.width() / 2)
            tilt = max(-2.5, min(2.5, dx / max(self.width(), 1) * 5))
            y_offset = -2
        elif self.state == "idle_glance":
            tilt = 1.5 * math.sin(elapsed * 2.8)
        elif self.state == "idle_scratch":
            tilt = 1.5 * math.sin(now * 11)
        elif self.state == "drag":
            tilt = 7 * math.sin(now * 14)
            y_offset = 5 * math.sin(now * 11)
            y_scale = 0.96
        elif self.state == "drop":
            y_scale = 1.06
        elif self.state == "tumble":
            tilt = 360 * min(1, elapsed / self.drop_duration)
            y_offset = -4 * math.sin(min(1, elapsed / self.drop_duration) * math.pi)
        elif self.state == "dizzy":
            tilt = 6 * math.sin(now * 13) * max(0, 1 - elapsed / 1.5)
        elif self.state == "play":
            tilt = 7 * math.sin(now * 11)
            y_offset = -9 * abs(math.sin(now * 9))
        elif self.state == "paw":
            tilt = 2.5 * math.sin(now * 9)
            y_offset = -2 * abs(math.sin(now * 9))
        elif self.state == "handshake_offer":
            tilt = 2 * math.sin(now * 5)
        elif self.state == "handshake":
            tilt = 3 * math.sin(now * 13)
            y_offset = -2 * abs(math.sin(now * 13))
        elif self.state == "happy":
            tilt = 2 * math.sin(now * 7)
            y_offset = -4 * abs(math.sin(now * 8))
        elif self.state == "bounce":
            if 0.12 <= elapsed < 0.55:
                y_offset = (
                    -42 * self.settings.scale / 100 * math.sin(math.pi * (elapsed - 0.12) / 0.43)
                )
        elif self.state == "eat":
            tilt = -4
            y_offset = 4 * abs(math.sin(now * 10))
        elif self.state == "annoyed":
            tilt = 2 * math.sin(now * 2)
        elif self.state == "yawn":
            tilt = -2
            y_scale = 1.01
        elif self.state == "lie":
            y_scale = 1.03 - 0.03 * min(1, elapsed / 1.1)
        elif self.state in {"sleep", "perch"}:
            y_scale = 1 + 0.007 * math.sin(now * 2)
        squash_x, squash_y = self._squash_scale(now)
        deform_x, deform_y = self._state_deformation(elapsed)
        x_scale *= squash_x * deform_x
        y_scale *= squash_y * deform_y
        return BodyMotion(tilt, y_offset, x_scale, y_scale)

    def _body_motion(self, now: float) -> BodyMotion:
        target = self._target_body_motion(now)
        transition = self._pose_transition
        if transition is None or transition.motion is None:
            return target
        progress = (now - transition.started) / transition.duration
        if progress >= 1:
            return target
        return transition.motion.toward(target, smoothstep(progress))

    def _pose_snapshot(self, now: float) -> QPixmap:
        snapshot = QPixmap(self.size())
        snapshot.fill(Qt.GlobalColor.transparent)
        painter = QPainter(snapshot)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._paint_pose(painter, now, self._body_motion(now))
        painter.end()
        return snapshot

    def _paint_pose(self, painter: QPainter, now: float, motion: BodyMotion) -> None:
        transition = self._pose_transition
        pixmap = self._active_pixmap()
        for layer, width_scale, height_scale, opacity in self._pose_layers(pixmap, now):
            if (
                transition is not None
                and transition.snapshot
                and layer.cacheKey() == transition.previous.cacheKey()
            ):
                painter.save()
                painter.setOpacity(opacity)
                painter.drawPixmap(0, 0, layer)
                painter.restore()
                continue
            scaled_x = motion.x_scale * width_scale
            scaled_y = motion.y_scale * height_scale
            center_x, center_y = self._pose_center(layer, scaled_x, scaled_y)
            painter.save()
            painter.setOpacity(opacity)
            if self.perch is not None:
                # The software frame hides the neck below the ledge, while
                # the two paw tips hang over its front edge.
                edge = self.normal_height - self.floor_padding - self.perch_overlap
                visible_width = self.pose_bounds[self.peek_pixmap.cacheKey()].width()
                clip = QRegion(0, 0, self.width(), edge)
                for side in (-1, 1):
                    paw_left = round(
                        self.width() / 2 + side * visible_width * 0.34 - visible_width * 0.15
                    )
                    clip = clip.united(
                        QRegion(paw_left, edge, round(visible_width * 0.3), self.height() - edge)
                    )
                painter.setClipRegion(clip)
            painter.translate(center_x, center_y + motion.y_offset)
            painter.rotate(motion.tilt)
            painter.scale(scaled_x, scaled_y)
            painter.drawPixmap(round(-layer.width() / 2), round(-layer.height() / 2), layer)
            if self.game_mode in {"catching", "returning"}:
                ratio = self.settings.scale / 100
                running = self.pose_families.get(layer.cacheKey()) == "run"
                mouth_x = layer.width() * ((0.16 if running else 0.35) - 0.5)
                mouth_y = layer.height() * (0.39 - 0.5)
                painter.setPen(
                    QPen(QColor("#207c91" if self.toy_kind == "frisbee" else "#9b452b"), 1.5)
                )
                painter.setBrush(QColor("#55cbd3" if self.toy_kind == "frisbee" else "#f3934d"))
                width = max(16, 36 * ratio) if self.toy_kind == "frisbee" else max(10, 20 * ratio)
                height = width * 0.35 if self.toy_kind == "frisbee" else width
                painter.drawEllipse(
                    QRectF(mouth_x - width / 2, mouth_y - height / 2, width, height)
                )
            painter.restore()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        painter = QPainter(self)
        painter.setCompositionMode(QPainter.CompositionMode_Source)
        painter.fillRect(self.rect(), Qt.GlobalColor.transparent)
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        now = time.monotonic()
        motion = self._body_motion(now)
        self._draw_shadow(painter, motion.y_offset)
        self._paint_pose(painter, now, motion)
        if self.settings.effects:
            painter.save()
            top = 0 if self.perch else self._bubble_rect().bottom() + 11
            painter.setClipRect(QRectF(0, top, self.width(), self.height() - top))
            self.particles.paint(painter)
            painter.restore()
        self._draw_emotion(painter, now)
        if self.perch is not None:
            return
        if self.state == "sleep":
            self._draw_bubble(painter, "Zzz…")
        elif self.bubble and now < self.bubble_until:
            self._draw_bubble(painter, self.bubble)

    def _draw_bubble(self, painter: QPainter, text: str) -> None:
        rect = self._bubble_rect()
        painter.setPen(QColor("#d9ab83"))
        painter.setBrush(QColor("#fffaf0"))
        painter.drawRoundedRect(rect, 14, 14)
        tail = QPainterPath()
        anchor = rect.left() + rect.width() * 0.28
        tail.moveTo(anchor, rect.bottom())
        tail.lineTo(anchor + 10, rect.bottom() + 10)
        tail.lineTo(anchor + 19, rect.bottom())
        painter.drawPath(tail)
        font = QFont()
        font.setPointSize(max(10, round(12 * self.settings.scale / 100)))
        painter.setFont(font)
        painter.setPen(QColor("#6c4632"))
        painter.drawText(
            rect.adjusted(10, 2, -10, -2),
            Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
            text,
        )
