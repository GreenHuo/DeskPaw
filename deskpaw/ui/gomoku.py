"""A resizable, locally played Gomoku board."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QDialog, QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from deskpaw.core.gomoku import SIZE, GomokuGame
from deskpaw.ui.theme import STYLE, icon, label


class GomokuBoard(QWidget):
    selected = Signal(int, int)

    def __init__(self, game: GomokuGame, parent=None) -> None:
        super().__init__(parent)
        self.game = game
        self.setMinimumSize(300, 300)
        self.setAccessibleName("五子棋棋盘，点击交叉点落子")

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(480, 480)

    def geometry_values(self) -> tuple[float, float, float]:
        side = min(self.width(), self.height()) - 40
        return (self.width() - side) / 2, (self.height() - side) / 2, side / (SIZE - 1)

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#ead0a3"))
        p.drawRoundedRect(QRectF(self.rect()), 12, 12)
        x, y, step = self.geometry_values()
        side = step * (SIZE - 1)
        p.setPen(QPen(QColor("#a38256"), 1))
        for i in range(SIZE):
            p.drawLine(QPointF(x, y + i * step), QPointF(x + side, y + i * step))
            p.drawLine(QPointF(x + i * step, y), QPointF(x + i * step, y + side))
        p.setBrush(QColor("#87683e"))
        for row, col in ((3, 3), (3, 11), (7, 7), (11, 3), (11, 11)):
            p.drawEllipse(QPointF(x + col * step, y + row * step), 3, 3)
        radius = step * 0.42
        for row in range(SIZE):
            for col in range(SIZE):
                stone = self.game.board[row][col]
                if not stone:
                    continue
                p.setPen(QPen(QColor("#35312d" if stone == 1 else "#b6aa98"), 1))
                p.setBrush(QColor("#302c28" if stone == 1 else "#fffdf7"))
                p.drawEllipse(QPointF(x + col * step, y + row * step), radius, radius)
        if self.game.moves:
            row, col = self.game.moves[-1]
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#d2854c"))
            p.drawEllipse(QPointF(x + col * step, y + row * step), 3, 3)
        p.end()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            return
        x, y, step = self.geometry_values()
        col = round((event.position().x() - x) / step)
        row = round((event.position().y() - y) / step)
        if (
            0 <= row < SIZE
            and 0 <= col < SIZE
            and abs(event.position().x() - x - col * step) <= step * 0.45
            and abs(event.position().y() - y - row * step) <= step * 0.45
        ):
            self.selected.emit(row, col)


class GomokuDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent, Qt.WindowType.Window)
        self.setWindowTitle("DeskPaw · 五子棋")
        self.setWindowIcon(icon("gomoku"))
        self.setStyleSheet(STYLE)
        self.game = GomokuGame()
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(320)
        self.timer.timeout.connect(self._computer_move)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        layout.addWidget(label("和柯基下五子棋", "Title"))
        rules = label("你执黑先手 · 柯基执白 · 横、竖或斜线连成五子获胜（无禁手）")
        rules.setWordWrap(True)
        layout.addWidget(rules)
        self.status = label("", "SectionTitle")
        layout.addWidget(self.status)
        self.board = GomokuBoard(self.game, self)
        self.board.selected.connect(self._human_move)
        layout.addWidget(self.board, 1)
        layout.addWidget(label("橙点标记最近一步 · 本地对弈，无需联网"))
        buttons = QHBoxLayout()
        self.undo = QPushButton("悔棋")
        self.undo.clicked.connect(self._undo)
        buttons.addWidget(self.undo)
        restart = QPushButton("重新开始")
        restart.setObjectName("Primary")
        restart.clicked.connect(self.reset)
        buttons.addWidget(restart)
        buttons.addStretch()
        close = QPushButton("结束游戏")
        close.clicked.connect(self.reject)
        buttons.addWidget(close)
        layout.addLayout(buttons)
        self.resize(530, 690)
        self._refresh()

    def reset(self) -> None:
        self.timer.stop()
        self.game = GomokuGame()
        self.board.game = self.game
        self._refresh()

    def stop(self) -> None:
        self.timer.stop()
        self.hide()

    def done(self, result: int) -> None:
        self.timer.stop()
        super().done(result)

    def _human_move(self, row: int, col: int) -> None:
        if self.game.turn != 1 or not self.game.play(row, col):
            return
        self._refresh()
        if not self.game.over:
            self.timer.start()

    def _computer_move(self) -> None:
        if self.game.turn != 2 or not self.isVisible():
            return
        move = self.game.choose_move()
        if move is not None:
            self.game.play(*move)
        self._refresh()

    def _undo(self) -> None:
        self.timer.stop()
        self.game.undo_round()
        self._refresh()

    def _refresh(self) -> None:
        if self.game.winner:
            text = "你赢啦！再来一局吧！" if self.game.winner == 1 else "柯基赢啦！再挑战一次？"
        elif self.game.over:
            text = "棋盘已满，平局！"
        else:
            text = "轮到你了，点击交叉点落子" if self.game.turn == 1 else "柯基正在思考…"
        self.status.setText(text)
        self.undo.setEnabled(bool(self.game.moves))
        self.board.setCursor(
            Qt.CursorShape.PointingHandCursor
            if self.game.turn == 1 and not self.game.over
            else Qt.CursorShape.ArrowCursor
        )
        self.board.update()
