"""Fetch, frisbee, light and snack game behavior for the pet window."""

from __future__ import annotations

import math
import random
import time

from PySide6.QtCore import QPoint
from PySide6.QtGui import (
    QCursor,
)

from deskpaw.pet.ball import BallWindow
from deskpaw.pet.toys import LightWindow, SnackWindow
from deskpaw.ui.gomoku import GomokuDialog


class PetGamesMixin:
    """Internal behavior of PetWindow; state and Qt lifetime belong to the window."""

    def start_gomoku_game(self) -> None:
        if self.game_mode == "gomoku" and self.gomoku is not None:
            self.gomoku.raise_()
            self.gomoku.activateWindow()
            return
        if not self._prepare_game():
            return
        if self.gomoku is None:
            self.gomoku = GomokuDialog(self)
            self.gomoku.finished.connect(self._gomoku_closed)
        self.gomoku.reset()
        self.game_mode = "gomoku"
        self._interact("look")
        self.gomoku.show()
        bounds = self.game_bounds
        self.gomoku.resize(
            min(self.gomoku.width(), bounds.width()),
            min(self.gomoku.height(), bounds.height()),
        )
        self.gomoku.move(bounds.center() - self.gomoku.rect().center())
        self.gomoku.raise_()
        self.gomoku.activateWindow()
        self.controls_changed.emit()
        self.say("一起下五子棋吧！你执黑先走。", 3)

    def _gomoku_closed(self) -> None:
        if self.game_mode == "gomoku":
            self.stop_game()

    def start_fetch_game(self, kind: str = "ball") -> None:
        if not self._prepare_game():
            return
        self.toy_kind = kind
        self.bond.reward("frisbee" if kind == "frisbee" else "ball")
        self._interact("happy")
        self.fetch_home_x = self.x()
        self.fetch_home_y = self.y()
        if self.ball is None:
            self.ball = BallWindow(self)
            self.ball.grabbed.connect(self._ball_grabbed)
            self.ball.released.connect(self._ball_released)
        self.ball.set_kind(kind)
        start_x = self.x() + self.width() // 2
        start_y = self.y() + self.normal_height - self.floor_padding - self.pet_pixmap.height() // 2
        self.ball.move(start_x, start_y)
        self.ball.show()
        self._throw_ball()
        self.say("飞盘来啦！看我接住！" if kind == "frisbee" else "球飞出去啦，等我捡回来！", 2)

    def _throw_ball(self, vx: float | None = None, vy: float | None = None) -> None:
        if self.ball is None:
            return
        self.game_bounds = self._screen().availableGeometry()
        self.ball_x = float(
            max(
                self.game_bounds.left(),
                min(self.game_bounds.right() - self.ball.width() + 1, self.ball.x()),
            )
        )
        self.ball_y = float(
            max(
                self.game_bounds.top(),
                min(self.game_bounds.bottom() - self.ball.height() + 1, self.ball.y()),
            )
        )
        left_room = self.ball_x - self.game_bounds.left()
        right_room = self.game_bounds.right() - self.ball_x - self.ball.width()
        if min(left_room, right_room) < 180:
            direction = 1 if right_room > left_room else -1
        else:
            direction = random.choice((-1, 1))
        self.ball_vx = direction * random.uniform(320, 480) if vx is None else vx
        self.ball_vy = -random.uniform(700, 950) if vy is None else vy
        self.game_mode = "flying"
        self._set_state("fetch")
        self.walk_distance = 0

    def _prepare_game(self) -> bool:
        if self.desktop.paused or self.desktop.locked:
            self.say("先恢复活动、解锁位置，再一起玩吧！")
            return False
        self._cancel_game()
        if self.perch is not None:
            self._leave_perch(to_desktop=False)
        self._rest_y = self.y()
        self.drop_from_y = None
        self.dragging = False
        self._sync_ground_span()
        self.game_bounds = self._screen().availableGeometry()
        self.move(
            max(
                self.game_bounds.left(), min(self.game_bounds.right() - self.width() + 1, self.x())
            ),
            max(
                self.game_bounds.top(),
                min(self.game_bounds.bottom() - self.normal_height + 1, self.y()),
            ),
        )
        self._rest_y = self.y()
        return True

    def _ball_grabbed(self) -> None:
        self.game_mode = "held"
        self._interact("look")

    def _ball_released(self, vx: float = 0.0, vy: float = 0.0) -> None:
        if self.game_mode != "held":
            return
        self.fetch_home_x = self.x()
        self.fetch_home_y = self.y()
        self._interact("happy")
        self._throw_ball(vx, vy)
        self.say("再来一次！", 1.4)

    def _cancel_game(self) -> None:
        self.game_mode = "off"
        if self.gomoku is not None:
            self.gomoku.stop()
        if self.ball is not None:
            self.ball.hide()
        if self.light is not None:
            self.light.hide()
        if self.snacks is not None:
            self.snacks.hide()
        self.snack_selected = None
        if self.state == "fetch":
            self._set_state("idle")

    def stop_game(self) -> None:
        self._cancel_game()
        self._interact("idle")
        self.say("休息一下，下次再玩！")

    def start_light_game(self) -> None:
        if not self._prepare_game():
            return
        if self.light is None:
            self.light = LightWindow(self)
        self.game_mode = "light"
        self.game_until = time.monotonic() + 30
        self.light_catches = 0
        self.light_last_target = None
        self.light_ready_at = 0
        self._interact("fetch")
        self.light.show()
        self._update_light(time.monotonic(), 0)
        self.say("在桌面任意位置移动鼠标，追到光点就算一分！", 3)

    def start_snack_game(self) -> None:
        if not self._prepare_game():
            return
        if self.snacks is None:
            self.snacks = SnackWindow(self)
            self.snacks.selected.connect(self._select_snack)
        self.snacks.reset()
        self.snack_answer = random.randrange(3)
        self.snack_opened.clear()
        self.snack_selected = None
        self.game_mode = "snack_wait"
        self.game_until = time.monotonic() + 60
        self._interact("look")
        bounds = self.game_bounds
        x = random.randint(
            bounds.left(), max(bounds.left(), bounds.right() - self.snacks.width() + 1)
        )
        y = random.randint(
            bounds.top(), max(bounds.top(), bounds.bottom() - self.snacks.height() + 1)
        )
        self.snacks.move(x, y)
        self.snacks.show()
        self.say("点一个杯子，我来找零食！", 3)

    def _select_snack(self, index: int) -> None:
        if self.game_mode != "snack_wait" or index in self.snack_opened:
            return
        self.snack_selected = index
        self.game_mode = "snack_seek"
        self._interact("fetch")
        self.snacks.hint.setText(f"柯基正在检查杯子 {index + 1}…")

    def _game_target(self, x: float, y: float) -> tuple[float, float]:
        """Place the dog's head near a toy anywhere on the desktop."""
        return (
            x - self.width() / 2,
            y - (self.normal_height - self.floor_padding - self.pet_pixmap.height() * 0.7),
        )

    def _run_to(self, target_x: float, dt: float, target_y: float | None = None) -> bool:
        if self.desktop.paused or self.desktop.locked:
            return False
        bounds = self.game_bounds
        target_x = max(bounds.left(), min(bounds.right() - self.width() + 1, target_x))
        target_y = (
            self.y()
            if target_y is None
            else max(bounds.top(), min(bounds.bottom() - self.normal_height + 1, target_y))
        )
        dx, dy = target_x - self.x(), target_y - self.y()
        distance = math.hypot(dx, dy)
        if distance <= 5:
            return True
        if abs(dx) > 1:
            self.direction = 1 if dx > 0 else -1
        step = min(distance, max(220, 280 * self.settings.scale / 100) * dt)
        candidate = QPoint(
            round(self.x() + dx / distance * step), round(self.y() + dy / distance * step)
        )
        self.walk_distance += math.hypot(candidate.x() - self.x(), candidate.y() - self.y())
        self._rest_y = candidate.y()
        self.move(candidate)
        self._sync_ground_span()
        return False

    def _update_light(self, now: float, dt: float) -> None:
        if now >= self.game_until:
            score = self.light_catches
            self._cancel_game()
            self._interact("happy")
            self.say(f"追光结束！我抓到了 {score} 次。", 3)
            return
        bounds = self.game_bounds
        pointer = QCursor.pos()
        target = QPoint(
            max(
                bounds.left() + self.light.width() // 2,
                min(bounds.right() - self.light.width() // 2, pointer.x()),
            ),
            max(
                bounds.top() + self.light.height() // 2,
                min(bounds.bottom() - self.light.height() // 2, pointer.y()),
            ),
        )
        self.light.move(target - QPoint(self.light.width() // 2, self.light.height() // 2))
        self.light.phase = now
        self.light.update()
        if now < self.light_ready_at:
            return
        target_x, target_y = self._game_target(target.x(), target.y())
        arrived = self._run_to(target_x, dt, target_y)
        if not arrived and now >= self.light_ready_at and self.state != "fetch":
            self._set_state("fetch")
        moved = (
            self.light_last_target is None
            or math.hypot(
                target.x() - self.light_last_target.x(), target.y() - self.light_last_target.y()
            )
            > 30
        )
        if arrived and moved and now >= self.light_ready_at:
            self.light_last_target = target
            self.light_ready_at = now + 1.5
            self.light_catches += 1
            self.bond.reward("light")
            self._interact("bounce")
            self.say(f"抓到光点啦！{self.light_catches} 分", 1.3)

    def _update_snacks(self, now: float, dt: float) -> None:
        if now >= self.game_until:
            self._cancel_game()
            self._interact("idle")
            return
        if self.game_mode != "snack_seek" or self.snack_selected is None:
            return
        index = self.snack_selected
        target = self.snacks.target(index)
        target_x = target.x() - self.width() / 2
        # Park beside the cups vertically so the pet's input region does
        # not cover the buttons after checking an empty cup.
        below = self.snacks.y() + self.snacks.height() + 6
        if below + self.normal_height <= self.game_bounds.bottom() + 1:
            target_y = below
        else:
            target_y = self.snacks.y() - self.normal_height - 6
        if not self._run_to(target_x, dt, target_y):
            return
        found = index == self.snack_answer
        self.snack_opened.add(index)
        self.snacks.reveal(index, found)
        self.snack_selected = None
        if found:
            self.bond.reward("snack")
            self._interact("eat")
            self.say("闻到啦！零食在这里！", 3)
            self.game_mode = "snack_done"
            self.game_until = now + 3
        else:
            self._interact("look")
            self.say("这个杯子没有，再找找！", 2)
            self.game_mode = "snack_wait"

    def _update_game(self, now: float, dt: float) -> None:
        if self.game_mode == "gomoku":
            return
        if self.game_mode == "light":
            self._update_light(now, dt)
            return
        if self.game_mode.startswith("snack_"):
            self._update_snacks(now, dt)
            return
        if self.ball is None or self.game_bounds is None:
            return
        if self.game_mode == "flying":
            frisbee = self.toy_kind == "frisbee"
            self.ball_vy += (360 if frisbee else 700) * dt
            self.ball_x += self.ball_vx * dt
            self.ball_y += self.ball_vy * dt
            left = self.game_bounds.left()
            right = self.game_bounds.right() - self.ball.width() + 1
            if self.ball_x < left or self.ball_x > right:
                self.ball_x = max(left, min(right, self.ball_x))
                self.ball_vx *= -0.65
            if self.ball_y < self.game_bounds.top():
                self.ball_y = float(self.game_bounds.top())
                self.ball_vy = abs(self.ball_vy) * 0.5
            floor = self.game_bounds.bottom() - self.ball.height() + 1
            target_x, target_y = self._game_target(
                self.ball_x + self.ball.width() / 2, self.ball_y + self.ball.height() / 2
            )
            self._run_to(target_x, dt, target_y)
            if frisbee:
                self.ball.spin += dt * 10
                self.ball.update()
            if now - self.state_since > 0.2:
                head_y = self.y() + self.pet_y + self.pet_pixmap.height() * 0.3
                near_x = abs(self.ball_x + self.ball.width() / 2 - self.x() - self.width() / 2) < 24
                near_y = abs(self.ball_y + self.ball.height() / 2 - head_y) < max(
                    36, self.pet_pixmap.height() * 0.45
                )
                if near_x and near_y:
                    self.ball.hide()
                    self.game_mode = "catching"
                    self.ball_wait_until = now + 0.7
                    self._interact("bounce")
                    self.say("跳起来接住飞盘啦！" if frisbee else "追到球啦！", 1.5)
                    return
            if self.ball_y >= floor:
                self.ball_y = floor
                if self.ball_vy > 110:
                    self.ball_vy *= -0.32
                    self.ball_vx *= 0.72
                else:
                    self.ball_vx = 0
                    self.ball_vy = 0
                    self.game_mode = "chasing"
                    self.roam_started = now
                    self.walk_distance = 0
                    self._set_state("fetch")
                    self.say("我来捡球！", 1.3)
            self.ball.move(round(self.ball_x), round(self.ball_y))
            return
        if self.game_mode == "waiting":
            if now >= self.ball_wait_until:
                self._cancel_game()
            return
        if self.game_mode == "catching":
            if now >= self.ball_wait_until:
                self.game_mode = "returning"
                self._set_state("fetch")
            return
        if self.game_mode not in {"chasing", "returning"}:
            return
        if self.game_mode == "chasing":
            target_x, target_y = self._game_target(
                self.ball.x() + self.ball.width() / 2, self.ball.y() + self.ball.height() / 2
            )
        else:
            target_x = self.fetch_home_x
            target_y = self.fetch_home_y
        if not self._run_to(target_x, dt, target_y):
            return
        if self.game_mode == "chasing":
            self.ball.hide()
            self.game_mode = "returning"
            self._effect_event("fetch_stop")
            self.roam_started = now
            self.say("捡到飞盘啦！" if self.toy_kind == "frisbee" else "找到球啦！", 1.3)
        else:
            self.game_mode = "waiting"
            self.ball_wait_until = now + 14
            self.ball.move(
                self.x() + self.width() // 2,
                self.y() + self.normal_height - self.floor_padding - self.ball.height(),
            )
            self.ball.show()
            self._interact("happy")
            self.say(
                "带回来啦！拖飞盘再丢一次。"
                if self.toy_kind == "frisbee"
                else "接住啦！拖球再丢一次。",
                3,
            )
