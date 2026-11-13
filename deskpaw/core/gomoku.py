"""Local freestyle Gomoku rules and a small tactical opponent."""

from __future__ import annotations

SIZE = 15
DIRECTIONS = ((0, 1), (1, 0), (1, 1), (1, -1))


class GomokuGame:
    """Black plays first; five or more consecutive stones wins, with no forbidden moves."""

    def __init__(self) -> None:
        self.board = [[0] * SIZE for _ in range(SIZE)]
        self.moves: list[tuple[int, int]] = []
        self.turn = 1
        self.winner = 0

    @property
    def over(self) -> bool:
        return bool(self.winner) or len(self.moves) == SIZE * SIZE

    def play(self, row: int, col: int) -> bool:
        if self.over or not (0 <= row < SIZE and 0 <= col < SIZE) or self.board[row][col]:
            return False
        self.board[row][col] = self.turn
        self.moves.append((row, col))
        if any(self._line(row, col, self.turn, dr, dc)[0] >= 5 for dr, dc in DIRECTIONS):
            self.winner = self.turn
        self.turn = 3 - self.turn
        return True

    def undo_round(self) -> None:
        """Return to the human's previous turn, including a pending computer response."""
        if not self.moves:
            return
        count = 1 if len(self.moves) % 2 else 2
        for _ in range(count):
            row, col = self.moves.pop()
            self.board[row][col] = 0
        self.winner = 0
        self.turn = 1

    def _line(self, row: int, col: int, player: int, dr: int, dc: int) -> tuple[int, int]:
        length, openings = 1, 0
        for sign in (-1, 1):
            r, c = row + sign * dr, col + sign * dc
            while 0 <= r < SIZE and 0 <= c < SIZE and self.board[r][c] == player:
                length += 1
                r, c = r + sign * dr, c + sign * dc
            if 0 <= r < SIZE and 0 <= c < SIZE and self.board[r][c] == 0:
                openings += 1
        return length, openings

    def _score(self, row: int, col: int, player: int) -> int:
        score = 0
        for dr, dc in DIRECTIONS:
            length, openings = self._line(row, col, player, dr, dc)
            if length >= 5:
                return 1_000_000
            if not openings:
                continue
            score += {
                (4, 2): 50_000,
                (4, 1): 8_000,
                (3, 2): 4_000,
                (3, 1): 200,
                (2, 2): 100,
                (2, 1): 20,
            }.get((length, openings), 2)
        return score

    def choose_move(self) -> tuple[int, int] | None:
        if self.over:
            return None
        if not self.moves:
            return SIZE // 2, SIZE // 2
        candidates = set()
        for row, col in self.moves:
            for r in range(max(0, row - 2), min(SIZE, row + 3)):
                for c in range(max(0, col - 2), min(SIZE, col + 3)):
                    if not self.board[r][c]:
                        candidates.add((r, c))

        def priority(cell: tuple[int, int]) -> tuple[int, int, int]:
            row, col = cell
            attack = self._score(row, col, self.turn)
            defend = self._score(row, col, 3 - self.turn)
            # Always take a win before blocking the other player's immediate win.
            tactical = 3 if attack >= 1_000_000 else 2 if defend >= 1_000_000 else 1
            return tactical, attack * 11 + defend * 10, -((row - 7) ** 2 + (col - 7) ** 2)

        return max(sorted(candidates), key=priority)
