import math
import unittest

from deskpaw.pet.ball import ThrowMotion


class ThrowTests(unittest.TestCase):
    def test_release_direction_strength_and_pause(self):
        slow, fast = ThrowMotion(), ThrowMotion()
        for motion, distance in ((slow, 12), (fast, 60)):
            motion.sample(100, 100, 0)
            motion.sample(100 - distance, 100 - distance / 2, 0.1)
        self.assertEqual(slow.velocity(0.1), (-120, -60))
        self.assertEqual(fast.velocity(0.1), (-600, -300))
        fast.sample(40, 70, 0.4)
        self.assertEqual(fast.velocity(0.4), (0, 0))

    def test_sparse_events_and_speed_limit(self):
        motion = ThrowMotion()
        motion.sample(0, 0, 0)
        motion.sample(40, 0, 0.2)
        self.assertAlmostEqual(motion.velocity(0.2)[0], 200)
        motion.sample(4000, 4000, 0.21)
        self.assertAlmostEqual(math.hypot(*motion.velocity(0.21)), 1800)
        self.assertEqual(motion.velocity(1), (0, 0))
