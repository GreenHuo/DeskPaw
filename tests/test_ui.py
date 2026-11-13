import os
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from deskpaw.config import Settings  # noqa: E402
from deskpaw.pet.window import PetWindow  # noqa: E402
from deskpaw.services.ai import ChatResponse  # noqa: E402
from deskpaw.ui.settings import SettingsDialog  # noqa: E402


class PetUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.pet = PetWindow(Settings(roam=False, idle_seconds=15))
        self.pet.show()
        self.app.processEvents()

    def tearDown(self):
        self.pet.tick_timer.stop()
        self.pet._cancel_game()
        self.pet.close()

    def test_click_and_idle_sequence(self):
        stamp = time.monotonic()
        self.pet.click_count = 1
        self.pet.last_click = stamp
        self.pet._resolve_click(stamp)
        self.assertEqual(self.pet.state, "paw")
        self.assertTrue(self.pet.bubble)
        self.pet.hovered = False
        self.pet._set_state("idle")
        self.pet.last_interaction = time.monotonic() - 16
        self.pet._tick()
        self.assertEqual(self.pet.state, "yawn")
        self.pet.state_since = time.monotonic() - 2
        self.pet._tick()
        self.assertEqual(self.pet.state, "lie")
        self.pet.state_since = time.monotonic() - 2
        self.pet._tick()
        self.assertEqual(self.pet.state, "sleep")
        self.assertFalse(self.pet._active_pixmap().isNull())

    def test_rewards_and_chat_actions_update_pet_and_expression(self):
        self.pet.action("eat", "开饭啦")
        self.assertEqual((self.pet.bond.mood, self.pet.bond.intimacy), (64, 3))
        self.pet.start_fetch_game()
        self.assertEqual((self.pet.bond.mood, self.pet.bond.intimacy), (76, 7))
        self.pet._chat_answered(ChatResponse("握个爪！", "handshake", "excited"))
        self.assertEqual(self.pet.state, "handshake")
        self.assertEqual(self.pet.emotion.kind, "heart")
        self.pet._chat_answered(ChatResponse("晚安", "sleep", "sleepy"))
        self.assertEqual(self.pet.state, "sleep")
        self.assertEqual(self.pet.emotion.kind, "snot")

    def test_seated_idle_actions_return_to_sitting(self):
        self.assertFalse(self.pet.sit_pixmap.isNull())
        self.assertEqual(self.pet._active_pixmap().cacheKey(), self.pet.sit_pixmap.cacheKey())
        poses = {
            "idle_blink": self.pet.sit_blink_pixmap,
            "idle_glance": self.pet.sit_look_pixmap,
            "idle_scratch": self.pet.sit_scratch_pixmap,
        }
        for state, pixmap in poses.items():
            self.assertFalse(pixmap.isNull())
            self.pet._set_state(state)
            self.assertEqual(self.pet._active_pixmap().cacheKey(), pixmap.cacheKey())
            self.pet.state_since = time.monotonic() - 2
            self.pet._tick()
            self.assertEqual(self.pet.state, "idle")
            self.assertEqual(self.pet._active_pixmap().cacheKey(), self.pet.sit_pixmap.cacheKey())

    def test_pose_transition_renders_and_expires(self):
        self.pet._set_state("happy")
        transition = self.pet._pose_transition
        self.assertEqual(transition.previous.cacheKey(), self.pet.sit_pixmap.cacheKey())
        self.assertEqual(transition.style, "bridge")
        early = self.pet._pose_layers(self.pet.happy_pixmap, transition.started + 0.04)
        late = self.pet._pose_layers(self.pet.happy_pixmap, transition.started + 0.15)
        self.assertEqual(len(early), 1)
        self.assertEqual(len(late), 1)
        self.assertEqual(early[0][0].cacheKey(), self.pet.sit_pixmap.cacheKey())
        self.assertEqual(late[0][0].cacheKey(), self.pet.happy_pixmap.cacheKey())
        self.assertLess(late[0][1], 1.0)
        middle = self.pet._pose_layers(self.pet.happy_pixmap, transition.started + 0.10)
        self.assertEqual(len(middle), 2)
        self.assertAlmostEqual(sum(layer[3] for layer in middle), 1.0)
        for layer, width_scale, height_scale, _ in (early[0], late[0]):
            _, center_y = self.pet._pose_center(layer, width_scale, height_scale)
            bounds = self.pet.pose_bounds[layer.cacheKey()]
            foot_y = center_y + (bounds.bottom() + 1 - layer.height() / 2) * height_scale
            self.assertAlmostEqual(foot_y, self.pet.normal_height - self.pet.floor_padding)
        with patch("deskpaw.pet.window.time.monotonic", return_value=transition.started + 0.06):
            self.pet.repaint()
        self.assertIsNotNone(self.pet._pose_transition)
        with patch("deskpaw.pet.window.time.monotonic", return_value=transition.started + 0.21):
            self.pet.repaint()
        self.assertIsNone(self.pet._pose_transition)

    def test_interrupt_uses_the_visible_pose_as_its_start(self):
        self.pet._set_state("happy")
        interrupted_at = self.pet._pose_transition.started + 0.07
        with patch("deskpaw.pet.window.time.monotonic", return_value=interrupted_at):
            expected = self.pet._pose_snapshot(interrupted_at).toImage()
            old_motion = self.pet._body_motion(interrupted_at)
            self.pet._set_state("sleep")
            transition = self.pet._pose_transition
            self.assertTrue(transition.snapshot)
            self.assertEqual(transition.previous.toImage(), expected)
            self.assertEqual(self.pet._pose_snapshot(interrupted_at).toImage(), expected)
            self.assertEqual(self.pet._body_motion(interrupted_at), old_motion)

    def test_body_motion_eases_with_pose(self):
        self.pet._set_state("eat")
        transition = self.pet._pose_transition
        start = self.pet._body_motion(transition.started)
        middle = self.pet._body_motion(transition.started + transition.duration / 2)
        end = self.pet._body_motion(transition.started + transition.duration)
        self.assertAlmostEqual(start.tilt, 0)
        self.assertGreater(middle.tilt, end.tilt)
        self.assertLess(middle.tilt, start.tilt)
        self.assertAlmostEqual(end.tilt, -4)

    def test_related_seated_poses_use_short_fade(self):
        self.pet._set_state("idle_blink")
        transition = self.pet._pose_transition
        self.assertEqual(transition.style, "fade")
        layers = self.pet._pose_layers(
            self.pet.sit_blink_pixmap, transition.started + transition.duration / 2
        )
        self.assertEqual(len(layers), 2)
        self.assertAlmostEqual(layers[0][3], 0.5)
        self.assertAlmostEqual(layers[1][3], 0.5)

    def test_drag_loop_blends_before_changing_frames(self):
        self.pet._set_state("drag")
        self.pet._pose_transition = None
        self.pet.state_since = 100.0
        layers = self.pet._pose_layers(self.pet.lift_pixmap, 100.0 + 0.18 * 0.75)
        self.assertEqual(len(layers), 2)
        self.assertEqual(layers[1][0].cacheKey(), self.pet.lift_b_pixmap.cacheKey())
        self.assertAlmostEqual(layers[0][3] + layers[1][3], 1.0)

    def test_random_idle_action_keeps_sleep_deadline(self):
        self.pet.last_interaction = time.monotonic() - 7
        self.pet.next_idle_action = time.monotonic() - 1
        with patch("deskpaw.pet.window.random.choice", return_value="idle_blink"):
            self.pet._tick()
        self.assertEqual(self.pet.state, "idle_blink")
        self.pet.state_since = time.monotonic() - 1
        self.pet._tick()
        self.assertEqual(self.pet.state, "idle")
        self.pet.last_interaction = time.monotonic() - 16
        self.pet.next_idle_action = time.monotonic() - 1
        self.pet._tick()
        self.assertEqual(self.pet.state, "yawn")

    def test_api_key_field_shows_status_without_revealing_saved_key(self):
        with patch("deskpaw.ui.settings.get_api_key", return_value=""):
            dialog = SettingsDialog(Settings())
        self.assertEqual(dialog.key_status.text(), "未配置 API Key")
        self.assertEqual(dialog.key.text(), "")
        dialog.key.setText("temporary-key")
        self.assertEqual(dialog.key_status.text(), "新密钥尚未保存")
        self.assertEqual(dialog.key.echoMode(), dialog.key.EchoMode.Password)
        dialog.key_visibility.click()
        self.assertEqual(dialog.key.echoMode(), dialog.key.EchoMode.Normal)
        dialog.key_visibility.click()
        self.assertEqual(dialog.key.echoMode(), dialog.key.EchoMode.Password)
        with (
            patch("deskpaw.ui.settings.get_api_key", return_value=""),
            patch("deskpaw.ui.settings.delete_api_key", return_value=True) as delete_key,
        ):
            dialog.delete_key.click()
        delete_key.assert_called_once_with("https://api.deepseek.com")
        self.assertEqual(dialog.key_status.text(), "未配置 API Key")
        dialog.close()

    def test_shadow_stays_on_floor_and_landing_rebounds(self):
        grounded, opacity = self.pet._shadow_geometry()
        floor = self.pet.y() + grounded.center().y()
        self.pet.move(self.pet.x(), self.pet._floor_y() - self.pet.pet_pixmap.height())
        self.pet._sync_ground_span()
        airborne, faded = self.pet._shadow_geometry()
        self.assertAlmostEqual(airborne.width() / grounded.width(), 0.45)
        self.assertAlmostEqual(faded / opacity, 0.25)
        self.assertEqual(self.pet.y() + airborne.center().y(), floor)
        self.assertGreater(self.pet.height(), self.pet.normal_height)
        self.pet._landing_impact()
        started = self.pet._squash[0]
        self.assertAlmostEqual(self.pet._squash_scale(started)[1], 0.86)
        self.assertGreater(self.pet._squash_scale(started + 0.125)[1], 1)
        self.assertEqual(self.pet._squash_scale(started + 0.5), (1, 1))

    def test_effect_switch_and_timed_emitters(self):
        self.pet.tick_timer.stop()
        self.pet._set_state("happy")
        self.assertEqual(self.pet.emotion.kind, "heart")
        self.assertEqual(len(self.pet.particles.particles), 3)
        self.pet.set_effects_enabled(False)
        self.assertIsNone(self.pet.emotion)
        self.assertFalse(self.pet.particles.particles)
        self.pet._set_state("annoyed")
        self.assertIsNone(self.pet.emotion)
        self.pet._landing_impact()
        self.assertIsNotNone(self.pet._squash)
        self.assertFalse(self.pet.particles.particles)
        self.pet.set_effects_enabled(True)
        self.pet._set_state("eat")
        started = self.pet.state_since
        with patch.object(self.pet, "_emit_specs") as emit:
            for elapsed in (0.05, 0.1, 0.4, 0.7, 1.0, 1.1):
                with patch("deskpaw.pet.window.time.monotonic", return_value=started + elapsed):
                    self.pet._tick()
            self.assertEqual(emit.call_count, 2)

    def test_resizing_and_chat_settings_keep_feet_on_ground(self):
        floor = self.pet.y() + self.pet.normal_height
        self.pet._apply_settings(Settings(scale=120, roam=False, effects=False))
        self.assertEqual(self.pet.y() + self.pet.normal_height, floor)
        self.assertFalse(self.pet.settings.effects)
        self.pet.open_chat()
        self.pet.chat.settings_changed.emit(Settings(scale=30, roam=False, effects=True))
        self.assertEqual(self.pet.settings.scale, 30)
        self.assertEqual(self.pet.y() + self.pet.normal_height, floor)
        self.pet.chat.close()

    def test_annoyed_uses_back_pose(self):
        self.pet._set_state("annoyed")
        self.assertEqual(self.pet._active_pixmap().cacheKey(), self.pet.back_pixmap.cacheKey())
        self.pet._set_state("sleep")
        self.assertEqual(self.pet._active_pixmap().cacheKey(), self.pet.sleep_pixmap.cacheKey())
        self.pet._set_state("drag")
        self.assertEqual(self.pet._active_pixmap().cacheKey(), self.pet.lift_pixmap.cacheKey())
        self.pet.state_since = time.monotonic() - 0.23
        self.assertEqual(self.pet._active_pixmap().cacheKey(), self.pet.lift_b_pixmap.cacheKey())

    def test_click_reactions_rotate_and_walk_frames_change(self):
        expected = ("paw", "happy", "bounce", "look", "paw")
        for state in expected:
            self.pet._set_state("idle")
            stamp = time.monotonic()
            self.pet.click_count = 1
            self.pet.last_click = stamp
            self.pet._resolve_click(stamp)
            self.assertEqual(self.pet.state, state)
        self.pet._set_state("idle")
        now = time.monotonic()
        self.pet.roam_started = now - 0.05
        self.pet.roam_until = now + 2
        self.pet.walk_distance = 0
        self.assertEqual(self.pet._active_pixmap().cacheKey(), self.pet.walk_a_pixmap.cacheKey())
        self.pet.walk_distance = 28 * self.pet.settings.scale / 100
        self.assertEqual(self.pet._active_pixmap().cacheKey(), self.pet.walk_b_pixmap.cacheKey())
        # Elapsed time alone must not move legs when the window is stationary.
        self.pet.roam_started = now - 20
        self.assertEqual(self.pet._active_pixmap().cacheKey(), self.pet.walk_b_pixmap.cacheKey())
        self.pet._set_state("fetch")
        run_frame = self.pet._active_pixmap()
        self.assertEqual(self.pet.run_gait.source.cacheKey(), self.pet.run_original.cacheKey())
        self.assertNotEqual(self.pet.run_original.cacheKey(), self.pet.original.cacheKey())
        self.assertIn(
            run_frame.cacheKey(), {frame.cacheKey() for frame in self.pet.run_gait.frames}
        )
        self.assertNotEqual(run_frame.cacheKey(), self.pet.walk_b_pixmap.cacheKey())
        self.pet.walk_distance += 24 * self.pet.settings.scale / 100
        self.assertNotEqual(self.pet._active_pixmap().cacheKey(), run_frame.cacheKey())
        self.pet.direction = -1
        self.assertEqual(self.pet._travel_facing_scale(), 1)
        self.pet.direction = 1
        self.assertEqual(self.pet._travel_facing_scale(), -1)

    def test_handshake_offer_accepts_a_click(self):
        self.pet.offer_handshake()
        self.assertEqual(self.pet.state, "handshake_offer")
        stamp = time.monotonic()
        self.pet.click_count = 1
        self.pet.last_click = stamp
        self.pet._resolve_click(stamp)
        self.assertEqual(self.pet.state, "handshake")
        self.assertIn("握手成功", self.pet.bubble)

    def test_roam_stride_tracks_distance_and_returns_to_sitting(self):
        self.pet.tick_timer.stop()
        self.pet.settings.roam = True
        now = time.monotonic()
        self.pet.next_roam = now - 1
        self.pet.last_tick_at = now - 0.04
        before = self.pet.x()
        with (
            patch("deskpaw.pet.window.time.monotonic", return_value=now),
            patch("deskpaw.pet.window.random.choice", return_value=-1),
        ):
            self.pet._tick()
        self.assertEqual(self.pet.walk_distance, 0, "散步应从静止平滑起步")
        with patch("deskpaw.pet.window.time.monotonic", return_value=now + 0.15):
            self.pet._tick()
        self.assertEqual(self.pet.walk_distance, abs(self.pet.x() - before))
        self.assertGreater(self.pet.walk_distance, 0)
        self.pet.roam_until = 0
        self.assertEqual(self.pet._active_pixmap().cacheKey(), self.pet.sit_pixmap.cacheKey())

    def test_walk_frames_have_distinct_rear_leg_silhouettes(self):
        a, b = self.pet.walk_a_pixmap.toImage(), self.pet.walk_b_pixmap.toImage()
        self.assertFalse(b.isNull())
        self.assertEqual(a.size(), b.size())
        changed, area = 0, 0
        for y in range(round(a.height() * 0.70), a.height()):
            for x in range(round(a.width() * 0.55), a.width()):
                area += 1
                changed += (a.pixelColor(x, y).alpha() > 128) != (b.pixelColor(x, y).alpha() > 128)
        self.assertGreater(changed / area, 0.15, "Rear paws must visibly exchange support roles")

    def test_ball_lands_and_pet_fetches_it(self):
        self.pet.start_fetch_game()
        self.assertEqual(self.pet.game_mode, "flying")
        self.assertTrue(self.pet.ball.isVisible())
        now = time.monotonic()
        for i in range(500):
            self.pet._update_game(now + i * 0.04, 0.04)
            if self.pet.game_mode == "waiting":
                break
        self.assertEqual(self.pet.game_mode, "waiting")
        self.assertTrue(self.pet.ball.isVisible())
        self.assertEqual(self.pet.state, "happy")
        self.assertGreater(self.pet.walk_distance, 0)
        self.pet._ball_grabbed()
        self.pet._ball_released()
        self.assertEqual(self.pet.game_mode, "flying")

    def test_ball_release_uses_pointer_velocity_and_screen_bounds(self):
        self.pet.start_fetch_game()
        self.pet.ball.grabbed.emit()
        self.pet.ball.move(self.pet.game_bounds.left() - 100, self.pet.game_bounds.top() - 100)
        self.pet.ball.released.emit(-600, -400)
        self.assertEqual((self.pet.ball_vx, self.pet.ball_vy), (-600, -400))
        now = time.monotonic()
        for i in range(1000):
            self.pet._update_game(now + i * 0.04, 0.04)
            if self.pet.game_mode == "waiting":
                break
        self.assertEqual(self.pet.game_mode, "waiting")
        self.assertGreaterEqual(self.pet.ball.x(), self.pet.game_bounds.left())
        self.assertLessEqual(
            self.pet.ball.x() + self.pet.ball.width() - 1, self.pet.game_bounds.right()
        )

    def test_mouse_flick_reaches_throw_physics(self):
        self.pet.start_fetch_game()
        ball = self.pet.ball
        origin = QPointF(ball.pos()) + QPointF(4, 4)
        events = (
            (
                QEvent.Type.MouseButtonPress,
                origin,
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.LeftButton,
            ),
            (
                QEvent.Type.MouseMove,
                origin + QPointF(30, -20),
                Qt.MouseButton.NoButton,
                Qt.MouseButton.LeftButton,
            ),
            (
                QEvent.Type.MouseButtonRelease,
                origin + QPointF(60, -40),
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.NoButton,
            ),
        )
        handlers = (ball.mousePressEvent, ball.mouseMoveEvent, ball.mouseReleaseEvent)
        for i, (kind, point, button, buttons) in enumerate(events):
            event = QMouseEvent(
                kind, QPointF(4, 4), point, button, buttons, Qt.KeyboardModifier.NoModifier
            )
            with patch("deskpaw.pet.ball.time.monotonic", return_value=10 + i * 0.05):
                handlers[i](event)
        self.assertEqual(self.pet.game_mode, "flying")
        self.assertAlmostEqual(self.pet.ball_vx, 600)
        self.assertAlmostEqual(self.pet.ball_vy, -400)

    def test_frisbee_catches_in_air_then_returns(self):
        self.pet.start_fetch_game("frisbee")
        now = time.monotonic()
        self.pet.state_since = now - 1
        self.pet.ball_x = self.pet.x() + self.pet.width() / 2 - self.pet.ball.width() / 2
        self.pet.ball_y = (
            self.pet.y()
            + self.pet.pet_y
            + self.pet.pet_pixmap.height() * 0.3
            - self.pet.ball.height() / 2
        )
        self.pet.ball_vx = self.pet.ball_vy = 0
        self.pet._update_game(now, 0)
        self.assertEqual(self.pet.game_mode, "catching")
        self.assertEqual(self.pet.state, "bounce")
        self.assertFalse(self.pet.ball.isVisible())
        self.pet._update_game(now + 0.8, 0.04)
        self.assertEqual(self.pet.game_mode, "returning")
        self.pet._update_game(now + 0.9, 0.04)
        self.assertEqual(self.pet.game_mode, "waiting")

    def test_light_scores_only_after_target_moves_and_times_out(self):
        target = QPoint(
            self.pet.x() + self.pet.width() // 2,
            round(self.pet.y() + self.pet.pet_y + self.pet.pet_pixmap.height() * 0.3),
        )
        now = time.monotonic()
        with patch("deskpaw.pet.games.QCursor.pos", return_value=target):
            self.pet.start_light_game()
            self.pet._update_game(now + 2, 0.04)
        self.assertEqual(self.pet.light_catches, 1)
        target.setX(target.x() - 80)
        with patch("deskpaw.pet.games.QCursor.pos", return_value=target):
            for i in range(50):
                self.pet._update_game(now + 3 + i * 0.04, 0.04)
        self.assertEqual(self.pet.light_catches, 2)
        self.pet._update_game(self.pet.game_until + 1, 0.04)
        self.assertEqual(self.pet.game_mode, "off")
        self.assertFalse(self.pet.light.isVisible())

    def test_snack_wrong_choice_then_find_and_switch_game(self):
        self.pet.tick_timer.stop()
        with patch("deskpaw.pet.window.random.randrange", return_value=1):
            self.pet.start_snack_game()
        self.app.processEvents()
        now = time.monotonic()
        self.pet.snacks.cups[0].click()
        for i in range(200):
            self.pet._update_game(now + i * 0.04, 0.04)
            if self.pet.game_mode == "snack_wait":
                break
        self.assertFalse(self.pet.snacks.cups[0].isEnabled())
        mood = self.pet.bond.mood
        self.pet.snacks.cups[1].click()
        for i in range(200):
            self.pet._update_game(now + 10 + i * 0.04, 0.04)
            if self.pet.game_mode == "snack_done":
                break
        self.assertEqual(self.pet.game_mode, "snack_done")
        self.assertEqual(self.pet.state, "eat")
        self.assertGreater(self.pet.bond.mood, mood)
        self.pet.start_light_game()
        self.assertFalse(self.pet.snacks.isVisible())
        self.pet.sleep()
        self.assertEqual(self.pet.game_mode, "off")
        self.assertFalse(self.pet.light.isVisible())

    def test_light_follows_vertical_pointer_motion_across_desktop(self):
        self.pet.tick_timer.stop()
        bounds = self.pet._screen().availableGeometry()
        target = QPoint(bounds.center().x(), bounds.top() + 180)
        home_y = self.pet.y()
        now = time.monotonic()
        with patch("deskpaw.pet.games.QCursor.pos", return_value=target):
            self.pet.start_light_game()
            for i in range(400):
                self.pet._update_game(now + i * 0.04, 0.04)
                if self.pet.light_catches:
                    break
        self.assertEqual(self.pet.light_catches, 1)
        self.assertLess(self.pet.y(), home_y - 100)
        self.assertAlmostEqual(self.pet.light.geometry().center().y(), target.y(), delta=1)
        self.assertTrue(bounds.contains(self.pet.geometry()))
        self.assertEqual(self.pet.height(), self.pet.normal_height)
        target.setY(target.y() + 180)
        with patch("deskpaw.pet.games.QCursor.pos", return_value=target):
            for i in range(200):
                self.pet._update_game(now + 17 + i * 0.04, 0.04)
                if self.pet.light_catches == 2:
                    break
        self.assertEqual(self.pet.light_catches, 2)
        position = self.pet.pos()
        self.pet._update_game(self.pet.game_until + 1, 0.04)
        self.assertEqual(self.pet.pos(), position)
        self.assertEqual(self.pet._floor_y(), position.y())

    def test_ball_and_frisbee_chase_above_floor_and_return_home_in_two_dimensions(self):
        self.pet.tick_timer.stop()
        for kind in ("ball", "frisbee"):
            with self.subTest(kind=kind):
                self.pet.start_fetch_game(kind)
                home = self.pet.pos()
                bounds = self.pet.game_bounds
                self.pet.ball_x = bounds.left() + 100
                self.pet.ball_y = bounds.top() + 100
                self.pet.ball_vx = self.pet.ball_vy = 0
                now = time.monotonic()
                minimum_y = home.y()
                for i in range(800):
                    self.pet._update_game(now + i * 0.04, 0.04)
                    minimum_y = min(minimum_y, self.pet.y())
                    self.assertTrue(bounds.contains(self.pet.geometry()))
                    if self.pet.game_mode == "waiting":
                        break
                self.assertLess(minimum_y, home.y() - 60)
                self.assertEqual(self.pet.game_mode, "waiting")
                self.assertAlmostEqual(self.pet.x(), home.x(), delta=5)
                self.assertAlmostEqual(self.pet.y(), home.y(), delta=5)
                self.assertEqual(self.pet.height(), self.pet.normal_height)
                self.pet.stop_game()

    def test_snacks_can_spawn_high_on_desktop_and_pet_leaves_buttons_clear(self):
        self.pet.tick_timer.stop()
        bounds = self.pet._screen().availableGeometry()
        with (
            patch(
                "deskpaw.pet.window.random.randint",
                side_effect=(bounds.left() + 50, bounds.top() + 90),
            ),
            patch("deskpaw.pet.window.random.randrange", return_value=1),
        ):
            self.pet.start_snack_game()
        self.app.processEvents()
        self.assertEqual(self.pet.snacks.y(), bounds.top() + 90)
        self.assertTrue(bounds.contains(self.pet.snacks.geometry()))
        self.pet.snacks.cups[0].click()
        now = time.monotonic()
        for i in range(400):
            self.pet._update_game(now + i * 0.04, 0.04)
            if self.pet.game_mode == "snack_wait":
                break
        self.assertEqual(self.pet.game_mode, "snack_wait")
        self.assertFalse(self.pet.geometry().intersects(self.pet.snacks.geometry()))
        self.assertLess(self.pet.y(), bounds.bottom() - self.pet.normal_height - 100)
        self.assertTrue(self.pet.snacks.cups[1].isEnabled())

    def test_chasing_and_returning_use_running_frames_and_speed(self):
        self.pet.start_fetch_game()
        self.pet.game_mode = "chasing"
        self.pet._set_state("fetch")
        self.pet.ball.move(self.pet.x() + self.pet.width() // 2 + 120, self.pet.ball.y())
        start_x = self.pet.x()
        self.pet._update_game(time.monotonic(), 0.1)
        chase_step = self.pet.x() - start_x
        self.assertGreater(chase_step, 50 * 0.1 * 2)
        self.assertIn(
            self.pet._active_pixmap().cacheKey(),
            {frame.cacheKey() for frame in self.pet.run_gait.frames},
        )
        self.pet.game_mode = "returning"
        self.pet.fetch_home_x = start_x
        self.pet._update_game(time.monotonic(), 0.1)
        self.assertEqual(self.pet.direction, -1)
        self.assertAlmostEqual(self.pet.x(), start_x, delta=1)
        self.assertIn(
            self.pet._active_pixmap().cacheKey(),
            {frame.cacheKey() for frame in self.pet.run_gait.frames},
        )

    def test_ambient_does_not_reset_sleep(self):
        self.pet._set_state("idle")
        self.pet.settings.idle_seconds = 60
        self.pet.last_interaction = time.monotonic() - 25
        self.pet.next_ambient = time.monotonic() - 1
        with patch("deskpaw.pet.window.random.random", return_value=0):
            self.pet._tick()
        self.assertTrue(self.pet.bubble)
        self.assertTrue(self.pet.ambient_reply)
        self.assertGreater(time.monotonic() - self.pet.last_interaction, 24)
        stamp = time.monotonic()
        self.pet.click_count = 1
        self.pet.last_click = stamp
        self.pet._resolve_click(stamp)
        self.assertEqual(self.pet.state, "happy")
        self.assertFalse(self.pet.ambient_reply)
        self.pet._set_state("idle")
        self.pet.last_interaction = time.monotonic() - 61
        self.pet._tick()
        self.assertEqual(self.pet.state, "yawn")

    def test_lying_pet_can_chat_without_standing_up_or_moving(self):
        self.pet.tick_timer.stop()
        self.pet.move(self.pet.x(), self.pet.y() - 180)
        self.pet.dragging = True
        self.pet._finish_drag()
        original = self.pet.pos()
        try:
            for state in ("lie", "sleep"):
                with self.subTest(state=state):
                    self.pet._set_state(state)
                    self.pet.open_chat()
                    self.assertTrue(self.pet.chat.isVisible())
                    self.assertEqual(self.pet.state, state)
                    self.pet._chat_answered(ChatResponse("听着呢，你慢慢说。", emotion="curious"))
                    self.assertEqual(self.pet.state, state)
                    self.assertEqual(self.pet.pos(), original)
                    self.pet._chat_answered(
                        ChatResponse("今天也很喜欢你。", action="happy", emotion="happy")
                    )
                    self.assertEqual(self.pet.state, state)
            self.pet._chat_answered(
                ChatResponse("给你小爪子！", action="handshake", emotion="happy")
            )
            self.assertEqual(self.pet.state, "handshake")
            self.assertEqual(self.pet.pos(), original)
        finally:
            self.pet.chat.close()


if __name__ == "__main__":
    unittest.main()
