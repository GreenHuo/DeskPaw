"""Rules, opponent tactics and desktop game lifecycle regression tests."""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QMenu  # noqa: E402

from deskpaw.config import Settings  # noqa: E402
from deskpaw.core.gomoku import SIZE, GomokuGame  # noqa: E402
from deskpaw.pet.window import PetWindow  # noqa: E402
from deskpaw.ui.controls import ControlDialog  # noqa: E402


class GomokuRulesTests(unittest.TestCase):
    def test_illegal_moves_do_not_change_turn(self):
        game = GomokuGame()
        self.assertFalse(game.play(-1, 0))
        self.assertFalse(game.play(0, SIZE))
        self.assertTrue(game.play(7, 7))
        self.assertFalse(game.play(7, 7))
        self.assertEqual(game.turn, 2)
        self.assertEqual(len(game.moves), 1)

    def test_five_in_each_direction_and_overline(self):
        for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
            with self.subTest(direction=(dr, dc)):
                game = GomokuGame()
                for i in range(5):
                    self.assertTrue(game.play(3 + i * dr, 7 + i * dc))
                    if i < 4:
                        game.play(14, i * 2)
                self.assertEqual(game.winner, 1)
                self.assertTrue(game.over)
                self.assertFalse(game.play(0, 0))
        game = GomokuGame()
        for col in (0, 1, 2, 4, 5):
            game.play(0, col)
            game.play(14, col * 2)
        game.play(0, 3)
        self.assertEqual(game.winner, 1)

    def test_undo_pending_response_pair_and_winning_move(self):
        game = GomokuGame()
        game.undo_round()
        game.play(7, 7)
        game.undo_round()
        self.assertEqual(game.moves, [])
        game.play(7, 7)
        game.play(7, 8)
        game.undo_round()
        self.assertEqual(game.moves, [])
        for i in range(4):
            game.play(0, i)
            game.play(14, i * 2)
        game.play(0, 4)
        game.undo_round()
        self.assertFalse(game.over)
        self.assertEqual(game.turn, 1)
        self.assertEqual(len(game.moves), 8)
        self.assertEqual(game.board[0][4], 0)

    def test_opponent_wins_before_defending(self):
        game = GomokuGame()
        for col in range(4):
            game.play(0, col)
            game.play(1, col)
        game.play(10, 10)
        self.assertEqual(game.choose_move(), (1, 4))
        game.play(*game.choose_move())
        self.assertEqual(game.winner, 2)

    def test_opponent_blocks_each_direction(self):
        for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
            with self.subTest(direction=(dr, dc)):
                game = GomokuGame()
                for i in range(4):
                    game.play(3 + i * dr, 7 + i * dc)
                    if i < 3:
                        game.play(14, i * 2)
                self.assertIn(
                    game.choose_move(),
                    ((3 - dr, 7 - dc), (3 + 4 * dr, 7 + 4 * dc)),
                )

    def test_draw_and_no_move_after_game(self):
        game = GomokuGame()
        # This pattern has no run of five in any direction.
        for row in range(SIZE):
            for col in range(SIZE):
                game.board[row][col] = 1 if (row + 2 * col) % 4 < 2 else 2
                game.moves.append((row, col))
        game.board[14][14] = 0
        game.moves.pop()
        game.turn = 1 if (14 + 2 * 14) % 4 < 2 else 2
        self.assertTrue(game.play(14, 14))
        self.assertEqual(game.winner, 0)
        self.assertTrue(game.over)
        self.assertIsNone(game.choose_move())


class GomokuUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.pet = PetWindow(Settings(roam=False))
        self.pet.show()
        self.pet.start_gomoku_game()
        self.app.processEvents()
        self.dialog = self.pet.gomoku

    def tearDown(self):
        self.pet.tick_timer.stop()
        self.pet._cancel_game()
        self.pet.close()

    def test_click_response_and_undo(self):
        x, y, step = self.dialog.board.geometry_values()
        QTest.mouseClick(
            self.dialog.board,
            Qt.MouseButton.LeftButton,
            pos=QPoint(round(x + step * 7), round(y + step * 7)),
        )
        self.assertEqual(self.dialog.game.board[7][7], 1)
        self.assertTrue(self.dialog.timer.isActive())
        self.dialog._human_move(6, 6)
        self.assertEqual(len(self.dialog.game.moves), 1)
        QTest.qWait(400)
        self.assertEqual(len(self.dialog.game.moves), 2)
        self.assertEqual(self.dialog.game.turn, 1)
        self.dialog.undo.click()
        self.assertEqual(self.dialog.game.moves, [])

    def test_reset_undo_and_switch_cancel_pending_response(self):
        for operation in (self.dialog.reset, self.dialog._undo):
            self.dialog._human_move(7, 7)
            operation()
            QTest.qWait(400)
            self.assertFalse(self.dialog.timer.isActive())
            self.assertEqual(self.dialog.game.moves, [])
        self.dialog._human_move(7, 7)
        self.pet.start_fetch_game()
        self.assertFalse(self.dialog.isVisible())
        self.assertFalse(self.dialog.timer.isActive())
        self.assertEqual(self.pet.game_mode, "flying")

    def test_close_restart_and_desktop_controls(self):
        self.dialog._human_move(7, 7)
        self.pet.start_gomoku_game()
        self.assertEqual(len(self.dialog.game.moves), 1)
        self.dialog.close()
        self.assertEqual(self.pet.game_mode, "off")
        self.assertFalse(self.dialog.timer.isActive())
        self.pet.start_gomoku_game()
        self.assertEqual(self.dialog.game.moves, [])
        self.pet.set_paused(True)
        self.assertFalse(self.dialog.isVisible())
        self.pet.start_gomoku_game()
        self.assertEqual(self.pet.game_mode, "off")
        self.pet.set_paused(False)
        self.pet.set_locked(True)
        self.pet.start_gomoku_game()
        self.assertEqual(self.pet.game_mode, "off")

    def test_game_menu_and_management_entry(self):
        menu = QMenu()
        self.pet.populate_menu(menu)
        games = next(action.menu() for action in menu.actions() if action.text() == "小游戏")
        self.assertIn("五子棋", [action.text() for action in games.actions()])
        panel = ControlDialog(self.pet)
        button = next(b for b in panel.game_buttons if b.accessibleName() == "五子棋")
        self.pet.stop_game()
        button.click()
        self.assertEqual(self.pet.game_mode, "gomoku")
        panel.close()
