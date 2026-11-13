"""Persistent mood and familiarity for the desktop companion."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from deskpaw.config.paths import settings_path

from .storage import read_json_object, write_json_object


def bond_path() -> Path:
    return settings_path().with_name("bond.json")


@dataclass
class Bond:
    mood: int = 50
    intimacy: int = 0
    path: Path | None = field(default=None, repr=False, compare=False)

    @classmethod
    def load(cls, path: Path | None = None) -> Bond:
        path = path or bond_path()
        data = read_json_object(path)
        return cls(_score(data.get("mood", 50), 50), _score(data.get("intimacy", 0), 0), path)

    def reward(self, activity: str) -> None:
        gains = {
            "feed": (14, 3),
            "pet": (6, 2),
            "ball": (12, 4),
            "handshake": (8, 3),
            "frisbee": (12, 4),
            "light": (3, 1),
            "snack": (10, 3),
        }
        mood, intimacy = gains[activity]
        self.mood = min(100, self.mood + mood)
        self.intimacy = min(100, self.intimacy + intimacy)
        if self.path is not None:
            self.save()

    def save(self) -> None:
        if self.path is None:
            return
        write_json_object(self.path, {"mood": self.mood, "intimacy": self.intimacy})

    @property
    def level(self) -> str:
        if self.mood < 35:
            return "quiet"
        if self.mood >= 70:
            return "cheerful"
        return "normal"

    def ambient_delay(self, rng) -> float:
        return rng.uniform(
            *{
                "quiet": (42, 65),
                "normal": (24, 42),
                "cheerful": (14, 25),
            }[self.level]
        )

    def idle_delay(self, rng) -> float:
        return rng.uniform(
            *{
                "quiet": (9, 15),
                "normal": (5, 10),
                "cheerful": (3, 6),
            }[self.level]
        )


def _score(value: object, default: int) -> int:
    try:
        return max(0, min(100, int(value)))
    except (TypeError, ValueError):
        return default
