"""A persistent menu-bar entry and a small fallback control window."""

from __future__ import annotations

from PySide6.QtCore import QObject, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QProgressBar,
    QPushButton,
    QSystemTrayIcon,
    QVBoxLayout,
)

from deskpaw.ui.theme import STYLE, avatar, card, icon, label


def paw_icon() -> QIcon:
    pixmap = QPixmap(32, 32)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#514137"))
    for rect in ((4, 9, 6, 9), (10, 3, 6, 10), (18, 3, 6, 10), (24, 9, 6, 9), (8, 17, 18, 12)):
        painter.drawEllipse(QRectF(*rect))
    painter.end()
    icon = QIcon(pixmap)
    icon.setIsMask(True)
    return icon


class ControlDialog(QDialog):
    def __init__(self, pet) -> None:
        super().__init__()
        self.pet = pet
        self.setWindowTitle("DeskPaw · 宠物管理")
        self.setFixedWidth(410)
        self.setStyleSheet(STYLE)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(12)
        header = QHBoxLayout()
        portrait = QLabel()
        portrait.setPixmap(avatar(52))
        header.addWidget(portrait)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        titles.addWidget(label("DeskPaw", "Title"))
        self.pet_label = label(f"{pet.settings.pet_name} · 陪在桌面的小伙伴")
        self.pet_label.setWordWrap(True)
        titles.addWidget(self.pet_label)
        header.addLayout(titles, 1)
        self.state_label = label("陪伴中", "Badge")
        header.addWidget(self.state_label, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addLayout(header)

        stats, stats_layout = card()
        stats_layout.setContentsMargins(18, 12, 18, 12)
        stats_layout.setSpacing(8)
        self.mood_label = label("", "SectionTitle")
        self.mood_bar = QProgressBar()
        self.mood_bar.setTextVisible(False)
        self.closeness_label = label("", "SectionTitle")
        self.closeness_bar = QProgressBar()
        self.closeness_bar.setObjectName("Closeness")
        self.closeness_bar.setTextVisible(False)
        stats_layout.addWidget(self.mood_label)
        stats_layout.addWidget(self.mood_bar)
        stats_layout.addWidget(self.closeness_label)
        stats_layout.addWidget(self.closeness_bar)
        layout.addWidget(stats)

        layout.addWidget(label("互动", "SectionTitle"))
        interactions = QHBoxLayout()
        for text, symbol, callback in (
            ("聊一聊", "chat", pet.open_chat),
            ("喂食", "feed", lambda: pet.action("eat", "嗷呜，谢谢你！")),
            ("握爪", "paw", pet.offer_handshake),
        ):
            button = QPushButton(icon(symbol, "#ffffff" if symbol == "chat" else "#9b623c"), text)
            button.clicked.connect(callback)
            if symbol == "chat":
                button.setObjectName("Primary")
            interactions.addWidget(button)
        layout.addLayout(interactions)

        games_title = QHBoxLayout()
        games_title.addWidget(label("小游戏", "SectionTitle"))
        games_title.addStretch()
        self.stop = QPushButton("结束游戏")
        self.stop.setObjectName("Quiet")
        self.stop.clicked.connect(pet.stop_game)
        games_title.addWidget(self.stop)
        layout.addLayout(games_title)
        games = QGridLayout()
        games.setSpacing(10)
        self.game_buttons = []
        for index, (text, symbol, hint, callback) in enumerate(
            (
                ("丢球", "ball", "甩手投球，追逐捡回", lambda: pet.start_fetch_game()),
                (
                    "接飞盘",
                    "frisbee",
                    "空中追赶，跳起接住",
                    lambda: pet.start_fetch_game("frisbee"),
                ),
                ("追光点", "light", "跟着你的鼠标跑", pet.start_light_game),
                ("找零食", "snack", "猜猜零食藏在哪", pet.start_snack_game),
            )
        ):
            button = QPushButton()
            button.setObjectName("GameTile")
            button.setMinimumHeight(86)
            button.setAccessibleName(text)
            button.setToolTip(hint)
            tile = QVBoxLayout(button)
            tile.setContentsMargins(14, 12, 12, 12)
            tile.setSpacing(7)
            row = QHBoxLayout()
            image = QLabel()
            image.setPixmap(icon(symbol).pixmap(QSize(22, 22)))
            row.addWidget(image)
            row.addWidget(label(text, "SectionTitle"), 1)
            tile.addLayout(row)
            tile.addWidget(label(hint))
            for child in button.findChildren(QLabel):
                child.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            button.clicked.connect(callback)
            games.addWidget(button, index // 2, index % 2)
            self.game_buttons.append(button)
        layout.addLayout(games)

        layout.addWidget(label("桌面控制", "SectionTitle"))
        row = QHBoxLayout()
        self.visibility = QPushButton()
        self.visibility.clicked.connect(pet.toggle_visibility)
        self.pause = QPushButton()
        self.pause.clicked.connect(lambda: pet.set_paused(not pet.desktop.paused))
        self.lock = QPushButton()
        self.lock.clicked.connect(lambda: pet.set_locked(not pet.desktop.locked))
        for button in (self.visibility, self.pause, self.lock):
            row.addWidget(button)
        layout.addLayout(row)
        footer = QHBoxLayout()
        self.more = QPushButton(icon("window"), "窗口停靠")
        self.more.setObjectName("Quiet")
        self.more.clicked.connect(self._more)
        settings = QPushButton(icon("settings"), "设置")
        settings.setObjectName("Quiet")
        settings.clicked.connect(pet.open_settings)
        footer.addWidget(self.more)
        footer.addStretch()
        footer.addWidget(settings)
        layout.addLayout(footer)
        pet.controls_changed.connect(self.refresh)
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(1000)
        self.refresh_timer.timeout.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        self.pet_label.setText(f"{self.pet.settings.pet_name} · 陪在桌面的小伙伴")
        visible = self.pet.isVisible()
        paused, locked = self.pet.desktop.paused, self.pet.desktop.locked
        self.visibility.setText("隐藏" if visible else "显示")
        self.visibility.setIcon(icon("hide" if visible else "show"))
        self.pause.setText("恢复" if paused else "暂停")
        self.pause.setIcon(icon("resume" if paused else "pause"))
        self.lock.setText("解锁" if locked else "锁定")
        self.lock.setIcon(icon("unlock" if locked else "lock"))
        mood = {"quiet": "低落", "normal": "平静", "cheerful": "开心"}[self.pet.bond.level]
        self.mood_label.setText(f"心情 · {mood}     {self.pet.bond.mood}/100")
        self.closeness_label.setText(f"亲密度               {self.pet.bond.intimacy}/100")
        self.mood_bar.setValue(self.pet.bond.mood)
        self.closeness_bar.setValue(self.pet.bond.intimacy)
        playing = self.pet.game_mode != "off"
        self.state_label.setText(
            "已隐藏" if not visible else "已暂停" if paused else "玩耍中" if playing else "陪伴中"
        )
        self.stop.setEnabled(playing)
        for button in self.game_buttons:
            button.setEnabled(not paused and not locked)
        self.more.setEnabled(not locked)

    def _more(self) -> None:
        menu = QMenu(self)
        menu.setStyleSheet(STYLE)
        self.pet.add_placement_actions(menu)
        menu.exec(self.more.mapToGlobal(self.more.rect().bottomLeft()))

    def showEvent(self, event) -> None:  # noqa: N802
        self.refresh()
        self.refresh_timer.start()
        super().showEvent(event)

    def hideEvent(self, event) -> None:  # noqa: N802
        self.refresh_timer.stop()
        super().hideEvent(event)

    def closeEvent(self, event) -> None:  # noqa: N802
        controls = self.pet.desktop_controls
        if not self.pet.isVisible() and (controls is None or not controls.tray.isVisible()):
            self.pet.show_pet()
        super().closeEvent(event)


class DesktopControls(QObject):
    def __init__(self, pet) -> None:
        super().__init__(pet)
        self.pet = pet
        self.panel = ControlDialog(pet)
        self.tray = QSystemTrayIcon(paw_icon(), self)
        self.tray.setToolTip("DeskPaw · 点击爪印打开快速控制")
        self.menu = QMenu()
        self.menu.setStyleSheet(STYLE)
        self.menu.aboutToShow.connect(self._populate)
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self._activated)
        self._populate()

    def start(self) -> None:
        self.panel.refresh()
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()
        else:
            self.panel.show()

    def _populate(self) -> None:
        self.menu.clear()
        self.pet.populate_menu(self.menu)

    def show_panel(self) -> None:
        self.panel.refresh()
        self.panel.show()
        self.panel.raise_()
        self.panel.activateWindow()

    def _activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.pet.toggle_visibility()
