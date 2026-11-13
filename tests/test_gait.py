import os
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSize
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication

from deskpaw.pet.gait import (
    LEGS,
    RunningGait,
    WalkingGait,
    foot_motion,
    running_foot_motion,
)


class GaitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_hind_feet_move_fore_and_aft_while_stance_stays_grounded(self):
        hind = [leg for leg in LEGS if "hind" in leg.name]
        for leg in hind:
            x_positions = [foot_motion(leg, i / 24)[3] for i in range(24)]
            self.assertGreater(max(x_positions) - min(x_positions), 70)
        for i in range(24):
            phase = i / 24
            grounded = sum(abs(foot_motion(leg, phase)[4] - leg.paw[1]) < 0.001 for leg in hind)
            self.assertGreaterEqual(grounded, 1)
            for leg in LEGS:
                lift = leg.paw[1] - foot_motion(leg, phase)[4]
                self.assertGreaterEqual(lift, -0.001)
                self.assertLessEqual(lift, 14.001)

    def test_cached_cycle_keeps_head_stable_and_alpha_clear(self):
        source = QPixmap(str(Path(__file__).parents[1] / "deskpaw" / "assets" / "corgi.png"))
        gait = WalkingGait(source, QSize(134, 112))
        self.assertEqual(len(gait.frames), 24)
        self.assertEqual(gait.frame_at(1).cacheKey(), gait.frame_at(0).cacheKey())
        self.assertNotEqual(gait.frame_at(0).cacheKey(), gait.frame_at(0.5).cacheKey())
        head = gait.frame_at(0).toImage().pixel(32, 30)
        for frame in gait.frames:
            image = frame.toImage()
            self.assertEqual(image.pixel(32, 30), head)
            self.assertEqual(image.pixelColor(0, 0).alpha(), 0)

    def test_run_has_longer_reach_higher_swing_and_a_separate_cycle(self):
        near_hind = next(leg for leg in LEGS if leg.name == "near_hind")
        walking = [foot_motion(near_hind, i / 48) for i in range(48)]
        running = [running_foot_motion(near_hind, i / 48) for i in range(48)]
        walk_reach = max(pose[3] for pose in walking) - min(pose[3] for pose in walking)
        run_reach = max(pose[3] for pose in running) - min(pose[3] for pose in running)
        self.assertGreater(run_reach, walk_reach * 2)
        self.assertGreater(max(near_hind.paw[1] - pose[4] for pose in running), 50)
        source = QPixmap(str(Path(__file__).parents[1] / "deskpaw" / "assets" / "corgi.png"))
        size = QSize(134, 112)
        walk_gait, run_gait = WalkingGait(source, size), RunningGait(source, size)
        self.assertEqual(len(run_gait.frames), 24)
        self.assertNotEqual(run_gait.frame_at(0.25).toImage(), walk_gait.frame_at(0.25).toImage())
        head = run_gait.frame_at(0).toImage().pixel(32, 30)
        self.assertTrue(all(frame.toImage().pixel(32, 30) == head for frame in run_gait.frames))


if __name__ == "__main__":
    unittest.main()
