import os
import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, QSize, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QMenu  # noqa: E402

from deskpaw.config import Settings  # noqa: E402
from deskpaw.core.desktop import DesktopState  # noqa: E402
from deskpaw.pet.window import PetWindow  # noqa: E402
from deskpaw.platform.surfaces import WindowSurface  # noqa: E402
from deskpaw.services.ai import ChatResponse  # noqa: E402
from deskpaw.ui.controls import DesktopControls  # noqa: E402


class Screen:
    def __init__(self, name, serial, rect):
        self._name, self._serial, self._rect = name, serial, rect

    def name(self):
        return self._name

    def serialNumber(self):
        return self._serial

    def geometry(self):
        return self._rect

    availableGeometry = geometry


class PlacementTests(unittest.TestCase):
    def test_monitor_restore_resize_removal_and_duplicate_names(self):
        first = Screen("Display", "", QRect(0, 0, 1200, 800))
        second = Screen("Display", "", QRect(-1600, -200, 1600, 1000))
        size = QSize(180, 200)
        state = DesktopState()
        position = QPoint(-1400, 300)
        state.capture(second, position, size)
        self.assertEqual(state.restore([first, second], size), position)
        resized = Screen("Display", "", QRect(-1000, -100, 1000, 700))
        restored = state.restore([first, resized], size)
        self.assertTrue(resized.geometry().contains(QRect(restored, size)))
        fallback = state.restore([first], size)
        self.assertTrue(first.geometry().contains(QRect(fallback, size)))

    def test_corrupt_data_and_preferences_round_trip(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "desktop.json"
            state = DesktopState(paused=True, locked=True, positioned=True, x=0.25, path=path)
            state.save()
            loaded = DesktopState.load(path)
            self.assertTrue(loaded.paused and loaded.locked and loaded.positioned)
            self.assertEqual(loaded.x, 0.25)
            path.write_text('{"x": "nan", "y": 999, "perch_id": "bad"}')
            loaded = DesktopState.load(path)
            self.assertEqual((loaded.x, loaded.y, loaded.perch_id), (0.8, 1, 0))


class Windows:
    error = ""

    def __init__(self, items=()):
        self.items = list(items)

    def windows(self):
        return self.items


class DesktopUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.provider = Windows()
        self.pet = PetWindow(Settings(idle_seconds=15), window_provider=self.provider)
        self.pet.show()
        self.app.processEvents()
        bounds = self.app.primaryScreen().availableGeometry()
        self.surface = WindowSurface(
            42,
            900,
            "测试程序",
            "窗口",
            QRect(bounds.left() + 40, bounds.top() + 300, min(600, bounds.width() - 80), 300),
        )
        self.provider.items = [self.surface]

    def tearDown(self):
        self.pet.shutdown()
        self.pet.close()

    def test_hide_show_and_fallback_panel_recovery(self):
        controls = DesktopControls(self.pet)
        self.pet.desktop_controls = controls
        controls.start()
        self.pet.start_fetch_game()
        self.pet.hide_pet()
        self.assertFalse(self.pet.isVisible())
        self.assertFalse(self.pet.tick_timer.isActive())
        self.assertFalse(self.pet.ball.isVisible())
        self.assertTrue(controls.panel.isVisible())
        controls.panel.visibility.click()
        self.assertTrue(self.pet.isVisible())
        self.assertTrue(self.pet.tick_timer.isActive())
        self.pet.hide_pet()
        controls.panel.close()
        self.assertTrue(self.pet.isVisible())

    def test_pause_and_lock_block_autonomy_and_drag(self):
        self.pet.set_paused(True)
        original = self.pet.pos()
        self.pet.last_interaction = time.monotonic() - 30
        self.pet.next_ambient = self.pet.next_roam = self.pet.next_idle_action = 0
        self.pet._tick()
        self.assertEqual(self.pet.state, "idle")
        self.assertEqual(self.pet.pos(), original)
        self.pet.start_light_game()
        self.assertEqual(self.pet.game_mode, "off")
        self.pet.set_paused(False)
        self.pet.set_locked(True)
        self.pet.press_global = self.pet.pos() + QPoint(30, 80)
        event = QMouseEvent(
            QEvent.Type.MouseMove,
            QPointF(30, 80),
            QPointF(self.pet.press_global + QPoint(100, -80)),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        self.pet.mouseMoveEvent(event)
        self.assertEqual(self.pet.pos(), original)
        self.assertFalse(self.pet.dragging)
        self.pet.start_fetch_game()
        self.assertEqual(self.pet.game_mode, "off")
        self.pet.set_locked(False)
        self.pet.start_fetch_game()
        self.assertEqual(self.pet.game_mode, "flying")

    def test_perch_tracks_move_resize_and_window_disappearing(self):
        self.pet.perch_on(self.surface, 0.3)
        original = self.pet.pos()
        self.assertEqual(self.pet.state, "perch")
        self.assertEqual(self.pet._active_pixmap().cacheKey(), self.pet.peek_pixmap.cacheKey())
        self.assertNotEqual(self.pet._active_pixmap().cacheKey(), self.pet.sleep_pixmap.cacheKey())
        self.assertEqual(
            self.pet.y() + self.pet.normal_height - self.pet.floor_padding - self.pet.perch_overlap,
            self.surface.rect.top(),
        )
        moved = replace(self.surface, rect=self.surface.rect.translated(20, 40))
        self.provider.items = [moved]
        self.pet._follow_perch()
        self.assertEqual(self.pet.pos() - original, QPoint(20, 40))
        self.pet._apply_settings(Settings(scale=120))
        self.assertEqual(
            self.pet.y() + self.pet.normal_height - self.pet.floor_padding - self.pet.perch_overlap,
            moved.rect.top(),
        )
        self.pet.repaint()
        self.provider.items = []
        self.pet._follow_perch()
        self.assertIsNone(self.pet.perch)
        self.assertEqual(self.pet.y(), self.pet._floor_y())
        self.assertEqual(self.pet.state, "idle")

    def test_drag_snaps_to_window_and_game_returns_to_desktop(self):
        self.pet.move(
            self.surface.rect.left() + 60,
            self.surface.rect.top() - self.pet.normal_height + self.pet.floor_padding + 10,
        )
        self.pet.dragging = True
        self.pet._finish_drag()
        self.assertEqual(self.pet.perch.identifier, 42)
        self.assertIsNone(self.pet.drop_from_y)
        self.pet.start_snack_game()
        self.assertIsNone(self.pet.perch)
        self.assertEqual(self.pet.game_mode, "snack_wait")
        self.assertEqual(self.pet.height(), self.pet.normal_height)
        self.assertTrue(self.pet.game_bounds.contains(self.pet.geometry()))

    def test_mouse_release_on_title_bar_snaps_when_feet_are_far_away(self):
        point = QPoint(self.surface.rect.center().x(), self.surface.rect.top() + 24)
        self.pet.move(point - QPoint(self.pet.width() // 2, 40))
        self.assertGreater(
            abs(
                self.pet.y()
                + self.pet.normal_height
                - self.pet.floor_padding
                - self.surface.rect.top()
            ),
            40,
        )
        self.pet.dragging = True
        event = QMouseEvent(
            QEvent.Type.MouseButtonRelease,
            QPointF(30, 40),
            QPointF(point),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
        self.pet.mouseReleaseEvent(event)
        self.assertEqual(self.pet.perch.identifier, self.surface.identifier)
        self.assertIsNone(self.pet.drop_from_y)
        self.assertAlmostEqual(self.pet.geometry().center().x(), point.x(), delta=2)

    def test_small_window_and_covered_window_edges(self):
        self.pet._apply_settings(Settings(scale=120))
        narrow = replace(
            self.surface,
            identifier=43,
            rect=QRect(self.surface.rect.left(), self.surface.rect.top(), 260, 220),
        )
        self.provider.items = [narrow]
        point = QPoint(narrow.rect.center().x(), narrow.rect.top() + 20)
        self.pet.dragging = True
        self.pet._finish_drag(point)
        self.assertEqual(self.pet.perch.identifier, narrow.identifier)
        self.pet.return_to_desktop()
        front = replace(narrow, identifier=44, rect=narrow.rect.translated(0, -80))
        self.provider.items = [front, narrow]
        self.pet.dragging = True
        self.pet._finish_drag(point)
        self.assertIsNone(self.pet.perch)

    def test_dragging_from_perch_keeps_dog_under_pointer(self):
        self.pet.perch_on(self.surface, 0.5)
        center = self.pet.geometry().center().x()
        point = QPoint(center, self.pet.y() + 30)
        self.pet.press_global = point
        self.pet.drag_offset = point - self.pet.pos()
        moved = point + QPoint(70, 40)
        event = QMouseEvent(
            QEvent.Type.MouseMove,
            QPointF(30, 40),
            QPointF(moved),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        self.pet.mouseMoveEvent(event)
        self.assertIsNone(self.pet.perch)
        self.assertTrue(self.pet.dragging)
        self.assertAlmostEqual(self.pet.geometry().center().x(), center + 70, delta=2)

    def test_drag_to_middle_stays_put_and_survives_restart(self):
        self.provider.items = []
        self.pet.settings.roam = False
        bounds = self.app.primaryScreen().availableGeometry()
        middle = QPoint(
            bounds.center().x() - self.pet.width() // 2,
            bounds.center().y() - self.pet.normal_height // 2,
        )
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "desktop.json"
            self.pet.desktop.path = path
            self.pet.move(middle)
            self.pet.dragging = True
            self.pet._finish_drag(middle + QPoint(40, 60))
            self.assertIsNone(self.pet.drop_from_y)
            self.assertEqual(self.pet.pos(), middle)
            self.assertEqual(self.pet.height(), self.pet.normal_height)
            for elapsed in (0.1, 0.5, 2, 10):
                with patch(
                    "deskpaw.pet.window.time.monotonic",
                    return_value=self.pet.last_interaction + elapsed,
                ):
                    self.pet._tick()
                self.assertEqual(self.pet.pos(), middle)
            another = PetWindow(
                Settings(roam=False), desktop=DesktopState.load(path), window_provider=self.provider
            )
            try:
                self.assertEqual(another.pos(), middle)
                self.assertEqual(another._floor_y(), middle.y())
            finally:
                another.shutdown()
                another.close()
            self.pet.desktop.path = None

    def test_perched_pet_chats_without_detaching_and_keeps_following_window(self):
        self.pet.perch_on(self.surface, 0.5)
        original = self.pet.pos()
        try:
            self.pet.open_chat()
            self.assertTrue(self.pet.chat.isVisible())
            self.pet._chat_answered(ChatResponse("我就在这里陪你。", emotion="happy"))
            self.assertEqual(self.pet.perch.identifier, self.surface.identifier)
            self.assertEqual(self.pet.state, "perch")
            self.assertEqual(self.pet.pos(), original)
            moved = replace(self.surface, rect=self.surface.rect.translated(15, 25))
            self.provider.items = [moved]
            self.pet._follow_perch()
            self.assertEqual(self.pet.pos() - original, QPoint(15, 25))
        finally:
            self.pet.chat.close()

    def test_peeking_head_and_two_paws_have_a_transparent_center_below_ledge(self):
        self.pet.perch_on(self.surface)
        image = self.pet.grab().toImage()
        edge = self.pet.normal_height - self.pet.floor_padding - self.pet.perch_overlap
        center = self.pet.width() // 2
        self.assertEqual(image.pixelColor(center, edge + 2).alpha(), 0)
        left = right = 0
        for y in range(edge + 2, self.pet.normal_height - self.pet.floor_padding):
            for x in range(image.width()):
                if image.pixelColor(x, y).alpha() > 32:
                    if x < center:
                        left += 1
                    else:
                        right += 1
        self.assertGreater(left, 0)
        self.assertGreater(right, 0)

    def test_menu_actions_and_top_edge_keep_body_visible(self):
        near_top = replace(self.surface, rect=self.surface.rect.translated(0, -290))
        self.provider.items = [near_top]
        menu = QMenu()
        self.pet.add_control_actions(menu)
        menu.actions()[1].trigger()
        self.assertTrue(self.pet.desktop.paused)
        menu.actions()[3].menu().actions()[0].trigger()
        self.assertEqual(self.pet.state, "perch")
        self.assertGreaterEqual(self.pet.y(), self.app.primaryScreen().availableGeometry().top())
        self.pet.repaint()

    def test_position_and_perch_survive_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "desktop.json"
            self.pet.desktop.path = path
            self.pet.perch_on(self.surface, 0.3)
            self.pet.set_paused(True)
            self.pet.set_locked(True)
            self.pet._save_position()
            another = PetWindow(
                Settings(), desktop=DesktopState.load(path), window_provider=self.provider
            )
            try:
                self.assertEqual(another.pos(), self.pet.pos())
                self.assertEqual(another.perch.identifier, 42)
                self.assertTrue(another.desktop.paused and another.desktop.locked)
                self.assertEqual(another.state, "perch")
            finally:
                another.shutdown()
                another.close()
            self.pet.desktop.path = None
