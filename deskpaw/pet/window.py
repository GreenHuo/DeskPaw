"""Transparent desktop pet with small animated reactions."""

from __future__ import annotations

import random
import sys
import time

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtGui import (
    QPixmap,
)
from PySide6.QtWidgets import QApplication, QMenu, QWidget

from deskpaw.config import Settings
from deskpaw.core.bond import Bond
from deskpaw.core.desktop import DesktopState
from deskpaw.core.resources import asset_path
from deskpaw.knowledge import KnowledgeService
from deskpaw.pet.ball import BallWindow
from deskpaw.pet.effects import EmotionMark, ParticleSystem
from deskpaw.pet.toys import LightWindow, SnackWindow
from deskpaw.platform.surfaces import WindowProvider, WindowSurface
from deskpaw.services.ai import ChatResponse
from deskpaw.ui.chat import ChatDialog
from deskpaw.ui.settings import SettingsDialog
from deskpaw.ui.theme import STYLE, add_action, icon

from .animation import PetAnimationMixin
from .constants import (
    AMBIENT_DIALOGUES,
    CLICK_REACTIONS,
    CLOSE_DIALOGUES,
    IDLE_ACTION_DURATION,
    IDLE_ACTIONS,
    MOOD_DIALOGUES,
    STATE_EFFECTS,
)
from .games import PetGamesMixin
from .motion import PoseTransition
from .placement import PetPlacementMixin

ASSET = asset_path("corgi.png")


class PetWindow(PetAnimationMixin, PetPlacementMixin, PetGamesMixin, QWidget):
    """Own Qt objects, runtime state, event handling and behavior coordination."""

    controls_changed = Signal()

    def __init__(
        self,
        settings: Settings,
        bond: Bond | None = None,
        desktop: DesktopState | None = None,
        window_provider=None,
        *,
        knowledge: KnowledgeService | None = None,
    ) -> None:
        super().__init__()
        self.settings = settings
        self.knowledge = knowledge
        self.bond = bond if bond is not None else Bond()
        self.desktop = desktop if desktop is not None else DesktopState()
        self.window_provider = (
            window_provider
            if window_provider is not None
            else WindowProvider(enabled=QApplication.platformName() != "offscreen")
        )
        self.perch: WindowSurface | None = None
        self.perch_ratio = self.desktop.perch_ratio
        self.perch_overlap = 0
        self._rest_y: int | None = None
        self._position_ready = False
        self._hidden = False
        self.desktop_controls = None
        self.original = QPixmap(str(ASSET))
        if self.original.isNull():
            raise FileNotFoundError(f"找不到宠物图片：{ASSET}")
        self.run_original = QPixmap(str(ASSET.with_name("corgi-run-facing.png")))
        if self.run_original.isNull():
            raise FileNotFoundError("找不到捡球朝向素材：corgi-run-facing.png")
        self.sleep_image = QPixmap(str(ASSET.with_name("corgi-sleep.png")))
        self.peek_image = QPixmap(str(ASSET.with_name("corgi-peek.png")))
        if self.peek_image.isNull():
            raise FileNotFoundError("找不到窗口上沿探头素材：corgi-peek.png")
        self.back_image = QPixmap(str(ASSET.with_name("corgi-back.png")))
        self.lift_image = QPixmap(str(ASSET.with_name("corgi-lift.png")))
        self.lift_b_image = QPixmap(str(ASSET.with_name("corgi-lift-b.png")))
        self.paw_image = QPixmap(str(ASSET.with_name("corgi-paw.png")))
        self.happy_image = QPixmap(str(ASSET.with_name("corgi-happy.png")))
        self.yawn_image = QPixmap(str(ASSET.with_name("corgi-yawn.png")))
        self.sit_image = QPixmap(str(ASSET.with_name("corgi-sit-front.png")))
        self.sit_blink_image = QPixmap(str(ASSET.with_name("corgi-sit-front-blink.png")))
        self.sit_look_image = QPixmap(str(ASSET.with_name("corgi-sit-front-look.png")))
        self.sit_scratch_image = QPixmap(str(ASSET.with_name("corgi-sit-front-scratch.png")))
        self.chat: ChatDialog | None = None
        self.ball: BallWindow | None = None
        self.light: LightWindow | None = None
        self.snacks: SnackWindow | None = None
        self.toy_kind = "ball"
        self.game_until = 0.0
        self.light_catches = 0
        self.light_last_target: QPoint | None = None
        self.light_ready_at = 0.0
        self.snack_answer = 0
        self.snack_selected: int | None = None
        self.snack_opened: set[int] = set()
        self.game_mode = "off"
        self.game_bounds = None
        self.fetch_home_x = 0
        self.fetch_home_y = 0
        self.ball_x = 0.0
        self.ball_y = 0.0
        self.ball_vx = 0.0
        self.ball_vy = 0.0
        self.ball_wait_until = 0.0
        self.state = "idle"
        self.state_since = time.monotonic()
        self.last_tick_at = self.state_since
        self.last_interaction = self.state_since
        self.next_ambient = self.state_since + self.bond.ambient_delay(random)
        self.next_roam = self.state_since + 8
        self.next_idle_action = self.state_since + self.bond.idle_delay(random)
        self.last_idle_action = ""
        self.roam_until = 0.0
        self.roam_started = 0.0
        self.walk_distance = 0.0
        self._pose_transition: PoseTransition | None = None
        self.direction = 1
        self.reaction_index = 0
        self.drag_offset = QPoint()
        self.press_global: QPoint | None = None
        self.dragging = False
        self.drop_from_y: int | None = None
        self.drop_started = 0.0
        self.drop_duration = 0.36
        self.bubble = ""
        self.bubble_until = 0.0
        self.ambient_reply = ""
        self.ambient_reply_until = 0.0
        self.click_count = 0
        self.last_click = 0.0
        self.hovered = False
        self.particles = ParticleSystem()
        self.emotion: EmotionMark | None = None
        self._squash: tuple[float, float, float, str] | None = None
        self._effect_events: list[tuple[float, str]] = []
        self.setWindowTitle("DeskPaw 柯基")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        # Qt's macOS tool panels otherwise disappear as soon as another
        # program becomes active, including when its title bar is dragged.
        self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow)
        self.setMouseTracking(True)
        self._resize_pet()
        self._place_initially()
        self.tick_timer = QTimer(self)
        self.tick_timer.timeout.connect(self._tick)
        self.tick_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.tick_timer.start(16)
        self.position_timer = QTimer(self)
        self.position_timer.setSingleShot(True)
        self.position_timer.timeout.connect(self._save_position)
        self.perch_timer = QTimer(self)
        self.perch_timer.timeout.connect(self._follow_perch)
        self.perch_timer.start(500)
        self._position_ready = True
        app = QApplication.instance()
        app.screenRemoved.connect(self._screens_changed)
        app.screenAdded.connect(self._screen_added)
        for screen in app.screens():
            screen.availableGeometryChanged.connect(self._screens_changed)

    def _set_state(self, state: str) -> None:
        now = time.monotonic()
        previous_pose, previous_motion, interrupted = self._transition_source(now)
        if self.emotion is not None:
            self.emotion.stop(now)
        self.state = state
        self.state_since = now
        self._begin_pose_transition(
            previous_pose, previous_motion, snapshot=interrupted, started=now
        )
        spec = STATE_EFFECTS.get(state, {})
        self._effect_events = list(spec.get("events", ()))
        if self.settings.effects:
            if "mark" in spec:
                kind, lifetime = spec["mark"]
                self.emotion = EmotionMark(kind, self.state_since, lifetime)
            self._emit_specs(spec.get("particles", ()))
        if state == "idle":
            self.next_idle_action = self.state_since + self.bond.idle_delay(random)
        self._update_mask()
        self.update()

    def _interact(self, state: str | None = None) -> None:
        self.last_interaction = time.monotonic()
        self.next_roam = self.last_interaction + 8
        self.next_idle_action = self.last_interaction + self.bond.idle_delay(random)
        self.next_ambient = self.last_interaction + self.bond.ambient_delay(random)
        if self.perch is not None and state != "perch":
            state = "perch"
        if state:
            self._set_state(state)
        elif self.state in {"sleep", "yawn", "lie"}:
            self._set_state("idle")
        self.roam_until = 0

    def say(self, text: str, seconds: float = 2.8) -> None:
        self.bubble = text
        self.bubble_until = time.monotonic() + seconds
        self._update_mask()
        self.update()

    def _tick(self) -> None:
        if self._hidden:
            return
        now = time.monotonic()
        dt = min(0.08, max(0.0, now - self.last_tick_at))
        self.last_tick_at = now
        if self.settings.effects:
            self.particles.update(dt)
        else:
            self.particles.clear()
            self.emotion = None
        if self.emotion is not None and not self.emotion.alive(now):
            self.emotion = None
        if self._squash is not None and now >= self._squash[0] + self._squash[2]:
            self._squash = None
        elapsed = now - self.state_since
        while self._effect_events and elapsed >= self._effect_events[0][0]:
            _, name = self._effect_events.pop(0)
            self._effect_event(name)
        if self.bubble and now >= self.bubble_until:
            self.bubble = ""
            self._update_mask()
        if self.drop_from_y is not None:
            progress = min(1.0, (now - self.drop_started) / self.drop_duration)
            eased = progress**2
            floor = self._floor_y()
            self.move(self.x(), round(self.drop_from_y + (floor - self.drop_from_y) * eased))
            self._sync_ground_span()
            if progress >= 1:
                self.drop_from_y = None
                if self.state == "tumble":
                    self._set_state("dizzy")
                    self._landing_impact(1.6)
                    self.say("晕乎乎…", 1.2)
                else:
                    self._set_state("idle")
                    self._landing_impact()
        if self.game_mode != "off":
            self._update_game(now, dt)
        elapsed = now - self.state_since
        if self.state == "yawn" and elapsed > 1.25:
            self._set_state("lie")
        elif self.state == "lie" and elapsed > 1.1:
            self._set_state("sleep")
        elif self.state == "handshake_offer" and elapsed > 4:
            self._set_state("idle")
        elif self.state in {
            "look",
            "paw",
            "happy",
            "bounce",
            "play",
            "eat",
            "annoyed",
            "handshake",
            "dizzy",
        } and elapsed > (3 if self.state == "annoyed" else 1.5):
            self._set_state("idle")
        elif self.state in IDLE_ACTION_DURATION and elapsed > IDLE_ACTION_DURATION[self.state]:
            self._set_state("idle")
        if self.perch is not None and self.state == "idle":
            self._set_state("perch")
        if self.desktop.paused or self.perch is not None:
            self.update()
            return
        if (
            self.state == "idle"
            and self.game_mode == "off"
            and not self.hovered
            and not self.dragging
            and now - self.last_interaction > self.settings.idle_seconds
        ):
            self.ambient_reply = ""
            self._set_state("yawn")
            self.say("哈啊～困了…", 1.2)
        if (
            self.settings.ambient_chatter
            and self.state == "idle"
            and self.game_mode == "off"
            and not self.hovered
            and now >= self.next_ambient
            and now - self.last_interaction < self.settings.idle_seconds - 8
        ):
            self._ambient_event(now)
        if (
            self.settings.roam
            and not self.desktop.locked
            and self.game_mode == "off"
            and self.state == "idle"
            and not self.hovered
            and not self.dragging
        ):
            if self.roam_until and now >= self.roam_until:
                previous, motion, interrupted = self._transition_source(now)
                self.roam_until = 0
                self._begin_pose_transition(previous, motion, snapshot=interrupted, started=now)
            if now >= self.next_roam and self.roam_until <= now:
                previous, motion, interrupted = self._transition_source(now)
                self.roam_started = now
                self.walk_distance = 0
                self.roam_x = float(self.x())
                self.roam_until = now + random.uniform(1.6, 3.0)
                self.next_idle_action = self.roam_until + self.bond.idle_delay(random)
                self.direction = random.choice((-1, 1))
                self.next_roam = now + random.uniform(11, 20)
                self._begin_pose_transition(previous, motion, snapshot=interrupted, started=now)
            if now < self.roam_until:
                if sys.platform != "darwin":
                    self._update_mask()
                bounds = self._screen().availableGeometry()
                ramp = min(1.0, (now - self.roam_started) / 0.25, (self.roam_until - now) / 0.25)
                self.roam_x += self.direction * 50 * dt * max(0.0, ramp)
                candidate = round(self.roam_x)
                if bounds.left() <= candidate <= bounds.right() - self.width() + 1:
                    self.walk_distance += abs(candidate - self.x())
                    self.move(candidate, self.y())
                else:
                    previous, motion, interrupted = self._transition_source(now)
                    self.roam_until = 0
                    self._begin_pose_transition(previous, motion, snapshot=interrupted, started=now)
                    self.next_idle_action = now + self.bond.idle_delay(random)
        if (
            self.state == "idle"
            and self.game_mode == "off"
            and not self.hovered
            and not self.dragging
            and now >= self.roam_until
            and now >= self.next_idle_action
            and now - self.last_interaction < self.settings.idle_seconds - 3
        ):
            choices = tuple(action for action in IDLE_ACTIONS if action != self.last_idle_action)
            action = random.choice(choices)
            self.last_idle_action = action
            self._set_state(action)
        self.update()

    def _ambient_event(self, now: float) -> None:
        self.next_ambient = now + self.bond.ambient_delay(random)
        chance = random.random()
        talk_limit, handshake_limit = {
            "quiet": (0.88, 0.97),
            "normal": (0.7, 0.9),
            "cheerful": (0.55, 0.8),
        }[self.bond.level]
        if chance < talk_limit:
            dialogues = MOOD_DIALOGUES.get(self.bond.level, AMBIENT_DIALOGUES)
            if self.bond.intimacy >= 30:
                dialogues += CLOSE_DIALOGUES
            line, reply = random.choice(dialogues)
            self.ambient_reply = reply
            self.ambient_reply_until = now + 8
            self._set_state(
                "look" if self.bond.level == "quiet" else random.choice(("look", "happy"))
            )
            self.say(line, 3)
        elif chance < handshake_limit:
            self.ambient_reply = ""
            self._set_state("handshake_offer")
            self.say("要不要握个爪？点我呀！", 3)
        else:
            self.ambient_reply = ""
            self._set_state("play")
            self.say("我想玩球了！右键选丢球～", 3)

    def offer_handshake(self) -> None:
        self._cancel_game()
        if self.perch is not None and not self.desktop.locked:
            self._leave_perch()
        self._interact("handshake_offer")
        self.say("来，点我握个爪！", 3)

    def enterEvent(self, event) -> None:  # noqa: N802 - Qt override
        self.hovered = True
        if self.state in {"idle", "sleep"}:
            self._interact("look")
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt override
        self.hovered = False
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.MouseButton.LeftButton:
            self.press_global = event.globalPosition().toPoint()
            self.drag_offset = self.press_global - self.pos()
            self.dragging = False
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self.desktop.locked:
            return super().mouseMoveEvent(event)
        if self.press_global is not None and event.buttons() & Qt.MouseButton.LeftButton:
            point = event.globalPosition().toPoint()
            if not self.dragging and (point - self.press_global).manhattanLength() > 9:
                self.dragging = True
                self._cancel_game()
                if self.perch is not None:
                    old_width = self.width()
                    old_height = self.normal_height
                    self._leave_perch(to_desktop=False)
                    self.drag_offset += QPoint(
                        (self.width() - old_width) // 2, self.normal_height - old_height
                    )
                self._rest_y = None
                self.drop_from_y = None
                self._interact("drag")
                self.say("哇，被拎起来啦！", 1.4)
            if self.dragging:
                destination = point - self.drag_offset
                destination.setY(min(destination.y(), self._floor_y()))
                self.move(destination)
                self._sync_ground_span()
                event.accept()
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.button() != Qt.MouseButton.LeftButton:
            return super().mouseReleaseEvent(event)
        self.press_global = None
        if self.dragging:
            self._finish_drag(event.globalPosition().toPoint())
            return
        now = time.monotonic()
        self.click_count = self.click_count + 1 if now - self.last_click < 0.75 else 1
        self.last_click = now
        if self.click_count >= 3:
            self.click_count = 0
            self._interact("annoyed")
            self.say("哼，别一直戳我！", 2.4)
        else:
            QTimer.singleShot(360, lambda stamp=now: self._resolve_click(stamp))

    def _finish_drag(self, release_point: QPoint | None = None) -> None:
        self.dragging = False
        if self.desktop.locked:
            return
        foot = self.y() + self.normal_height - self.floor_padding
        center_x = self.x() + self.width() / 2
        peek_width = max(72, self.pose_bounds[self.peek_pixmap.cacheKey()].width() + 24)
        surfaces = self.window_provider.windows()
        # Pointer-first snapping lets users grab any part of the dog and
        # release on the title bar, including windows near the screen top.
        anchors = [(release_point.x(), release_point.y())] if release_point is not None else []
        anchors.append((center_x, foot))
        for anchor_x, anchor_y in anchors:
            for index, surface in enumerate(surfaces):
                edge = QPoint(round(anchor_x), surface.rect.top())
                if (
                    surface.rect.width() >= peek_width
                    and surface.rect.left() <= anchor_x <= surface.rect.right()
                    and abs(anchor_y - surface.rect.top()) <= 40
                    and not any(front.rect.contains(edge) for front in surfaces[:index])
                ):
                    ratio = (anchor_x - peek_width / 2 - surface.rect.left()) / max(
                        1, surface.rect.width() - peek_width
                    )
                    self.perch_on(surface, ratio)
                    return
        bounds = self._screen().availableGeometry()
        position = QPoint(
            max(bounds.left(), min(bounds.right() - self.width() + 1, self.x())),
            max(bounds.top(), min(bounds.bottom() - self.normal_height + 1, self.y())),
        )
        self.drop_from_y = None
        self._rest_y = position.y()
        self.move(position)
        self._sync_ground_span()
        self._interact("idle")
        self.say("就在这里陪你。", 1.4)
        self.position_timer.stop()
        self._save_position()

    def _resolve_click(self, stamp: float) -> None:
        if stamp != self.last_click:
            return
        count = self.click_count
        self.click_count = 0
        if count == 1:
            self.bond.reward("pet")
            if self.perch is not None:
                self._interact("perch")
                if self.settings.effects:
                    self.emotion = EmotionMark("heart", time.monotonic(), 1.4)
                return
            if self.state in {"paw", "handshake_offer"}:
                self.bond.reward("handshake")
                self._interact("handshake")
                self.say("握手成功！好朋友！", 2)
                return
            if self.ambient_reply and time.monotonic() < self.ambient_reply_until:
                reply = self.ambient_reply
                self.ambient_reply = ""
                self._interact("happy")
                self.say(reply, 2.5)
                return
            state, words = CLICK_REACTIONS[self.reaction_index % len(CLICK_REACTIONS)]
            self.reaction_index += 1
            self._interact(state)
            self.say(words, 1.8)
        elif count == 2:
            self.open_chat()

    def populate_menu(self, menu: QMenu) -> None:
        mood_label = {"quiet": "低落", "normal": "平静", "cheerful": "开心"}[self.bond.level]
        status = add_action(
            menu, f"心情 {mood_label} {self.bond.mood} · 亲密度 {self.bond.intimacy}", "pet"
        )
        status.setEnabled(False)
        menu.addSeparator()
        add_action(menu, "聊一聊", "chat", self.open_chat)
        interactions = menu.addMenu("互动")
        interactions.setIcon(icon("paw"))
        add_action(interactions, "握爪", "paw", self.offer_handshake)
        add_action(interactions, "喂食", "feed", lambda: self.action("eat", "嗷呜，谢谢你！"))
        add_action(interactions, "逗它玩", "play", lambda: self.action("play", "好耶！一起玩！"))
        add_action(interactions, "睡觉", "sleep", self.sleep)
        games = menu.addMenu("小游戏")
        games.setIcon(icon("ball"))
        blocked = self.desktop.paused or self.desktop.locked
        for title, symbol, callback in (
            ("丢球", "ball", lambda: self.start_fetch_game()),
            ("接飞盘", "frisbee", lambda: self.start_fetch_game("frisbee")),
            ("追光点", "light", self.start_light_game),
            ("找零食", "snack", self.start_snack_game),
        ):
            add_action(games, title, symbol, callback).setEnabled(not blocked)
        games.addSeparator()
        add_action(games, "结束游戏", "stop", self.stop_game).setEnabled(self.game_mode != "off")
        desktop = menu.addMenu("桌面控制")
        desktop.setIcon(icon("window"))
        self.add_control_actions(desktop)
        menu.addSeparator()
        if self.desktop_controls is not None:
            add_action(menu, "宠物管理", "pet", self.desktop_controls.show_panel)
        add_action(menu, "设置", "settings", self.open_settings)
        add_action(menu, "退出", "quit", QApplication.instance().quit)

    def contextMenuEvent(self, event) -> None:  # noqa: N802 - Qt override
        menu = QMenu(self)
        menu.setStyleSheet(STYLE)
        self.populate_menu(menu)
        menu.exec(event.globalPos())

    def action(self, state: str, words: str) -> None:
        self._cancel_game()
        if self.perch is not None and not self.desktop.locked:
            self._leave_perch()
        if state == "eat":
            self.bond.reward("feed")
        elif state == "play":
            self.bond.reward("ball")
        self._interact(state)
        self.say(words)

    def sleep(self) -> None:
        self._cancel_game()
        if self.perch is not None and not self.desktop.locked:
            self._leave_perch()
        self._interact("yawn")
        self.say("晚安，做个好梦。", 1.5)

    def open_chat(self) -> None:
        self._cancel_game()
        self._interact(self.state if self.state in {"perch", "lie", "sleep"} else "look")
        if self.chat is None:
            self.chat = ChatDialog(self.settings, bond=self.bond, knowledge=self.knowledge)
            self.chat.settings_changed.connect(self._apply_settings)
            self.chat.answer_ready.connect(self._chat_answered)
        self.chat.show()
        self.chat.raise_()
        self.chat.activateWindow()

    def _chat_answered(self, response: ChatResponse) -> None:
        self._cancel_game()
        action = response.action
        if action == "sleep":
            self._cancel_game()
            if self.perch is not None and not self.desktop.locked:
                self._leave_perch()
            self._interact("sleep")
        elif action == "handshake":
            if self.perch is not None and not self.desktop.locked:
                self._leave_perch()
            self.bond.reward("handshake")
            self._interact("handshake")
        elif action == "play":
            self.start_fetch_game()
        elif action == "eat":
            self.action("eat", response.reply)
        elif action == "happy":
            self._interact(self.state if self.state in {"perch", "lie", "sleep"} else "happy")
        else:
            self._interact(self.state if self.state in {"perch", "lie", "sleep"} else "look")
        if self.settings.effects and action != "sleep":
            mark = {
                "happy": "heart",
                "curious": "question",
                "excited": "heart",
                "sleepy": "snot",
            }.get(response.emotion)
            if mark is not None:
                self.emotion = EmotionMark(mark, time.monotonic(), 1.6)
        self.say(response.reply[:36] + ("…" if len(response.reply) > 36 else ""), 3)

    def open_settings(self) -> None:
        dialog = SettingsDialog(self.settings)
        if dialog.exec() == dialog.DialogCode.Accepted:
            self._apply_settings(dialog.settings)

    def _apply_settings(self, settings: Settings) -> None:
        self._cancel_game()
        old_bottom = self.y() + self.normal_height
        self.settings = settings
        self.set_effects_enabled(settings.effects)
        self._resize_pet()
        self.move(self.x(), old_bottom - self.normal_height)
        if self.perch is not None:
            self.move(self._perch_position(self.perch))
        elif self._rest_y is not None:
            self._rest_y = self.y()
        if self.chat is not None:
            self.chat.settings = self.settings
            self.chat._refresh_identity()
        self.controls_changed.emit()
        self.say("新设置记住啦！")
        self._save_position()

    def shutdown(self) -> None:
        self._save_position()
        self.position_timer.stop()
        self.perch_timer.stop()
        self.tick_timer.stop()
        self._cancel_game()
        if self.chat is not None and self.chat.worker is not None:
            self.chat.worker.resolve_approval(False)
            self.chat.worker.wait(46_000)
        if self.desktop_controls is not None:
            self.desktop_controls.tray.hide()
            self.desktop_controls.panel.hide()
