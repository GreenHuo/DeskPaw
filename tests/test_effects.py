import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from deskpaw.pet.effects import EmotionMark, ParticleSystem, symbol_pixmap


class EffectsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_velocity_gravity_damping_and_rotation(self):
        system = ParticleSystem()
        particle = system.spawn(
            "dust", 10, 20, vx=100, vy=-30, gravity=50, damp=2, angular_velocity=90, lifetime=2
        )
        system.update(0.1)
        self.assertAlmostEqual(particle.vx, 80)
        self.assertAlmostEqual(particle.vy, -19)
        self.assertAlmostEqual(particle.x, 18)
        self.assertAlmostEqual(particle.y, 18.1)
        self.assertAlmostEqual(particle.angle, 9)

    def test_lifetime_and_hard_limit_evict_oldest(self):
        system = ParticleSystem()
        for i in range(100):
            system.spawn("heart", i, 0, lifetime=0.5)
        self.assertEqual(len(system.particles), 80)
        self.assertEqual(system.particles[0].x, 20)
        system.update(0.5)
        self.assertFalse(system.particles)

    def test_ring_stays_fixed_and_opacity_fades(self):
        system = ParticleSystem()
        particle = system.spawn("ring", 10, 20, vx=100, vy=200, gravity=100, lifetime=1)
        system.update(0.5)
        self.assertEqual((particle.x, particle.y), (10, 20))
        self.assertAlmostEqual(particle.opacity, 0.25)
        system.clear()
        self.assertFalse(system.particles)

    def test_emotion_entrance_exit_and_persistent_sleep(self):
        mark = EmotionMark("heart", 10, 1.4)
        self.assertAlmostEqual(mark.appearance(10)[0], 0.6)
        self.assertAlmostEqual(mark.appearance(10.195)[0], 1.08)
        self.assertAlmostEqual(mark.appearance(10.3)[0], 1)
        self.assertAlmostEqual(mark.appearance(11.5)[1], 0.5)
        self.assertFalse(mark.alive(11.7))
        sleeping = EmotionMark("snot", 10, None)
        self.assertTrue(sleeping.alive(1000))
        sleeping.stop(1000)
        self.assertFalse(sleeping.alive(1000.3))

    def test_all_vector_shapes_cache_at_display_scale(self):
        for kind in (
            "heart",
            "note",
            "anger",
            "star",
            "exclaim",
            "question",
            "snot",
            "sparkle",
            "dust",
            "crumb",
            "ring",
        ):
            pixmap = symbol_pixmap(kind, 30, 1.5)
            self.assertFalse(pixmap.isNull())
            self.assertEqual(pixmap.width(), 45)
            self.assertEqual(pixmap.deviceIndependentSize().width(), 30)
            self.assertEqual(pixmap.cacheKey(), symbol_pixmap(kind, 30, 1.5).cacheKey())


if __name__ == "__main__":
    unittest.main()
