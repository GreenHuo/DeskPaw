"""Screen placement, visibility controls and native-window perching."""

from __future__ import annotations

import time

from PySide6.QtCore import QPoint, QSize
from PySide6.QtWidgets import QApplication, QMenu

from deskpaw.platform.surfaces import WindowSurface
from deskpaw.ui.theme import add_action, icon


class PetPlacementMixin:
    """Internal behavior of PetWindow; state and Qt lifetime belong to the window."""

    def _screen(self):
        body_y = (
            self.normal_height // 2 if self.perch else self.pet_y + self.pet_pixmap.height() // 2
        )
        center = self.pos() + QPoint(self.width() // 2, body_y)
        return QApplication.screenAt(center) or QApplication.primaryScreen()

    def _floor_y(self) -> int:
        if self.perch is not None:
            return self._perch_position(self.perch).y()
        if self._rest_y is not None:
            return self._rest_y
        return self._screen().availableGeometry().bottom() - self.normal_height + 1

    def _sync_ground_span(self) -> None:
        """Keep the physical floor inside this same window during drag/drop."""
        height = self.normal_height + max(0, self._floor_y() - self.y())
        if self.height() != height:
            self.resize(self.width(), height)
        self._update_mask()

    def _place_initially(self) -> None:
        if self.desktop.positioned:
            self.move(self.desktop.restore(QApplication.screens(), self.size()))
            self._rest_y = self.y()
            if self.desktop.perch_id:
                surface = next(
                    (
                        window
                        for window in self.window_provider.windows()
                        if window.identifier == self.desktop.perch_id
                        and window.pid == self.desktop.perch_pid
                    ),
                    None,
                )
                if surface is not None:
                    self.perch = surface
                    self._resize_pet()
                    self.move(self._perch_position(surface))
                    self._set_state("perch")
                    self._pose_transition = None
                else:
                    self._rest_y = None
                    self.move(self.x(), self._floor_y())
            return
        rect = QApplication.primaryScreen().availableGeometry()
        self.move(rect.right() - self.width() - 60, rect.bottom() - self.height() + 1)

    def moveEvent(self, event) -> None:  # noqa: N802
        super().moveEvent(event)
        if self._position_ready:
            self.position_timer.start(500)

    def _save_position(self) -> None:
        self.desktop.capture(self._screen(), self.pos(), QSize(self.width(), self.normal_height))
        self.desktop.perch_id = self.perch.identifier if self.perch else 0
        self.desktop.perch_pid = self.perch.pid if self.perch else 0
        self.desktop.perch_ratio = self.perch_ratio
        try:
            self.desktop.save()
            self.setToolTip("DeskPaw 桌面柯基")
        except OSError:
            self.setToolTip("位置暂时无法保存，请检查 DeskPaw 配置目录的写入权限")

    def _screen_added(self, screen) -> None:
        screen.availableGeometryChanged.connect(self._screens_changed)
        self._screens_changed()

    def _screens_changed(self, *args) -> None:
        if not self._position_ready:
            return
        screens = QApplication.screens()
        if not screens:
            return
        self._cancel_game()
        self.drop_from_y = None
        self.dragging = False
        self.press_global = None
        self.roam_until = 0
        if self.perch is not None:
            self._follow_perch()
        elif not any(s.availableGeometry().contains(self.geometry()) for s in screens):
            self.move(self.desktop.restore(screens, QSize(self.width(), self.normal_height)))
            self._rest_y = self.y()
            self._sync_ground_span()
        self._save_position()

    def hide_pet(self) -> None:
        self._cancel_game()
        self.roam_until = 0
        self.drop_from_y = None
        self.dragging = False
        self.press_global = None
        if self.perch is None:
            self._rest_y = self.y()
        self._sync_ground_span()
        self._save_position()
        self._hidden = True
        self.tick_timer.stop()
        self.hide()
        if self.chat is not None:
            self.chat.hide()
        if self.desktop_controls is not None and not self.desktop_controls.tray.isVisible():
            self.desktop_controls.show_panel()
        self.controls_changed.emit()

    def show_pet(self) -> None:
        self._hidden = False
        self.last_tick_at = time.monotonic()
        self._follow_perch()
        self._interact("perch" if self.perch else "idle")
        self.show()
        self.raise_()
        self.tick_timer.start(16)
        self.controls_changed.emit()

    def toggle_visibility(self) -> None:
        self.hide_pet() if self.isVisible() else self.show_pet()

    def set_paused(self, paused: bool) -> None:
        self.desktop.paused = paused
        self._cancel_game()
        self.roam_until = 0
        self.drop_from_y = None
        if self.perch is None:
            self._rest_y = self.y()
        self._sync_ground_span()
        self._interact("perch" if self.perch else "idle")
        self.say("活动已暂停。" if paused else "我回来啦，继续陪你！")
        self._save_position()
        self.controls_changed.emit()

    def set_locked(self, locked: bool) -> None:
        self.desktop.locked = locked
        if locked:
            self._cancel_game()
            self.roam_until = 0
            self.drop_from_y = None
            self.dragging = False
            self.press_global = None
            if self.perch is None:
                self._rest_y = self.y()
            self._sync_ground_span()
            self._interact("perch" if self.perch else "idle")
        self.say("位置已锁定。" if locked else "现在可以拖动我啦！")
        self._save_position()
        self.controls_changed.emit()

    def _perch_position(self, surface: WindowSurface) -> QPoint:
        screen = QApplication.screenAt(surface.rect.center()) or self._screen()
        available = screen.availableGeometry()
        x = surface.rect.left() + round(
            self.perch_ratio * max(0, surface.rect.width() - self.width())
        )
        x = max(available.left(), min(available.right() - self.width() + 1, x))
        y = max(
            available.top(),
            surface.rect.top() + self.floor_padding + self.perch_overlap - self.normal_height,
        )
        y = min(available.bottom() - self.normal_height + 1, y)
        return QPoint(x, y)

    def perch_on(self, surface: WindowSurface, ratio: float | None = None) -> None:
        if self.desktop.locked:
            self.say("先解锁位置，再选择窗口吧。")
            return
        self._cancel_game()
        self.drop_from_y = None
        self.roam_until = 0
        self._rest_y = None
        self.perch = surface
        if ratio is not None:
            self.perch_ratio = max(0, min(1, ratio))
        self._resize_pet()
        self.move(self._perch_position(surface))
        self._sync_ground_span()
        self._interact("perch")
        self._pose_transition = None
        self._save_position()
        self.controls_changed.emit()

    def _leave_perch(self, to_desktop: bool = True) -> None:
        foot = self.y() + self.normal_height
        center_x = self.x() + self.width() // 2
        self.perch = None
        self._rest_y = None
        self._resize_pet()
        self.move(
            self.x() if to_desktop else center_x - self.width() // 2,
            self._floor_y() if to_desktop else foot - self.normal_height,
        )
        self._sync_ground_span()
        self._set_state("idle")
        self.controls_changed.emit()

    def return_to_desktop(self) -> None:
        if self.desktop.locked:
            self.say("先解锁位置，就能回到桌面啦。")
            return
        self._cancel_game()
        self._leave_perch()
        self._interact("idle")
        self._save_position()

    def _follow_perch(self) -> None:
        if self.perch is None or self._hidden or self.dragging:
            return
        surface = next(
            (
                window
                for window in self.window_provider.windows()
                if window.identifier == self.perch.identifier and window.pid == self.perch.pid
            ),
            None,
        )
        if surface is None:
            self._leave_perch()
            self._interact("idle")
            self._save_position()
            return
        self.perch = surface
        self.move(self._perch_position(surface))

    def add_control_actions(self, menu: QMenu) -> None:
        add_action(
            menu,
            "隐藏宠物" if self.isVisible() else "显示宠物",
            "hide" if self.isVisible() else "show",
            self.toggle_visibility,
        )
        pause = add_action(menu, "暂停活动", "pause")
        pause.setCheckable(True)
        pause.setChecked(self.desktop.paused)
        pause.triggered.connect(self.set_paused)
        lock = add_action(menu, "锁定位置", "lock")
        lock.setCheckable(True)
        lock.setChecked(self.desktop.locked)
        lock.triggered.connect(self.set_locked)
        self.add_placement_actions(menu)

    def add_placement_actions(self, menu: QMenu) -> None:
        windows = menu.addMenu("趴到程序窗口上")
        windows.setIcon(icon("window"))
        windows.setEnabled(not self.desktop.locked)
        surfaces = [w for w in self.window_provider.windows() if w.rect.width() >= self.width()]
        if not surfaces:
            unavailable = windows.addAction(self.window_provider.error or "暂无可停靠的程序窗口")
            unavailable.setEnabled(False)
        for surface in surfaces:
            add_action(
                windows,
                surface.label.replace("&", "&&"),
                "window",
                lambda s=surface: self.perch_on(s),
            )
        back = add_action(menu, "回到桌面", "home", self.return_to_desktop)
        back.setEnabled(
            not self.desktop.locked and (self.perch is not None or self._rest_y is not None)
        )
