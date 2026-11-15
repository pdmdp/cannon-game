"""Core checks added for repository publication; no game window is started."""
from pathlib import Path
import hashlib
import json
import math
import os
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from game import constants as C, physics, projectiles, storage


class PhysicsChecks(unittest.TestCase):
    def test_segment_distance_and_degenerate_segment(self):
        self.assertEqual(physics.point_segment_dist2(2, 3, 0, 0, 4, 0), 9)
        self.assertEqual(physics.point_segment_dist2(3, 4, 0, 0, 0, 0), 25)

    def test_swept_contact_between_endpoints(self):
        self.assertTrue(physics.segment_circle_hit(-10, 0, 10, 0, 0, 0, 1))
        self.assertFalse(physics.segment_circle_hit(-10, 2, 10, 2, 0, 0, 1))

    def test_crossing_and_parallel_segments(self):
        self.assertEqual(physics.segment_intersection(0, 0, 4, 0, 2, -2, 2, 2), (0.5, 2, 0))
        self.assertIsNone(physics.segment_intersection(0, 0, 4, 0, 0, 1, 4, 1))

    def test_reflection_preserves_speed(self):
        n = 1 / math.sqrt(2)
        vx, vy = physics.reflect(3, 4, n, n)
        self.assertAlmostEqual(vx * vx + vy * vy, 25)
        self.assertEqual((vx, vy), physics.reflect(3, 4, -n, -n))

    def test_ballistic_step_and_preview(self):
        p = projectiles.Bullet(20, 50, 200, 300)
        dt, n = 0.01, 10
        for _ in range(n):
            p.update(dt)
        self.assertAlmostEqual(p.x, 20 + 200 * n * dt)
        self.assertAlmostEqual(p.y, 50 + 300 * n * dt - C.GRAVITY * dt * dt * n * (n - 1) / 2)
        points = physics.simulate_trajectory(20, 50, 200, 300, True, n * dt, dt, n)
        self.assertAlmostEqual(points[-2], p.x)
        self.assertAlmostEqual(points[-1], p.y)

    def test_laser_and_top_boundary(self):
        p = projectiles.Laser(0, 0, 100, 200)
        p.update(0.1)
        self.assertEqual((p.x, p.y, p.vy), (10, 20, 200))
        top = C.SCREEN_HEIGHT + C.FIELD_MARGIN + 1
        self.assertTrue(projectiles.Laser(100, top, 0, 100).out_of_field())
        self.assertFalse(projectiles.Bullet(100, top, 0, 100).out_of_field())

    def test_beam_length_through_a_corner(self):
        p = projectiles.Laser(0, 0, 100, 0)
        p.add_bounce(100, 0)
        p.x, p.y = 100, 30
        points = p.beam_points()
        length = sum(math.hypot(points[i+2]-points[i], points[i+3]-points[i+1])
                     for i in range(0, len(points)-2, 2))
        self.assertAlmostEqual(length, C.LASER_IMPULSE)
        p.reset_path(100, 30)
        self.assertEqual(p.path, [(100, 30)])


class StorageChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.previous_env = os.environ.pop('CANNON_DATA_DIR', None)
        self.previous_dir = storage.DATA_DIR
        storage.configure(self.temp.name)

    def tearDown(self):
        storage.configure(self.previous_dir)
        if self.previous_env is not None:
            os.environ['CANNON_DATA_DIR'] = self.previous_env
        self.temp.cleanup()

    def test_settings_roundtrip_and_validation(self):
        settings = dict(storage.DEFAULT_SETTINGS, player_name='  Ada  ', music_volume=2, sfx_volume=float('nan'))
        storage.save_settings(settings)
        self.assertEqual(storage.load_settings(), settings)
        self.assertEqual(settings['player_name'], 'Ada')
        self.assertEqual(settings['music_volume'], 1.0)
        self.assertEqual(settings['sfx_volume'], storage.DEFAULT_SETTINGS['sfx_volume'])
        self.assertFalse(list(Path(self.temp.name).glob('*.tmp')))

    def test_corrupt_settings_fall_back(self):
        Path(storage.SETTINGS_FILE).write_text('{invalid json')
        self.assertEqual(storage.load_settings(), storage.DEFAULT_SETTINGS)

    def test_profile_reset_preserves_preferences_and_files(self):
        settings = dict(storage.DEFAULT_SETTINGS, player_name='Ada', intro_seen=True,
                        profile_created=True, reduced_motion=True, music_volume=0.2)
        Path(storage.SAVE_SLOT_FILES[1]).write_text('preserve me')
        storage.reset_profile(settings)
        self.assertFalse(settings['intro_seen'])
        self.assertTrue(settings['reduced_motion'])
        self.assertEqual(settings['music_volume'], 0.2)
        self.assertEqual(Path(storage.SAVE_SLOT_FILES[1]).read_text(), 'preserve me')

    def test_save_slots_and_rejected_geometry(self):
        from game import levels
        obstacles, target = levels.build_level(0, 0)
        snapshot = {'version': 3, 'level_index': 0, 'phase': 0, 'campaign_difficulty': 'normal',
                    'shots_total': 0, 'shots_round': 0, 'shots_left': levels.shot_budget(0, 'normal'),
                    'cannon': {'angle': 45, 'velocity': 300, 'projectile': 'bullet'},
                    'target': {'x': target[0], 'y': target[1], 'sprite': 'sprite_beacon'},
                    'obstacles': [x.to_dict() for x in obstacles]}
        storage.save_game(snapshot, slot=1, player_name='Ada')
        self.assertEqual(storage.load_game(slot=1)['cannon'], snapshot['cannon'])
        self.assertEqual([x['status'] for x in storage.list_save_slots()], ['valid', 'empty', 'empty'])
        snapshot['target']['x'] += 1
        with self.assertRaises(ValueError):
            storage.save_game(snapshot, slot=2, player_name='Ada')
        self.assertEqual(storage.load_game(slot=1)['target']['x'], target[0])


class AssetChecks(unittest.TestCase):
    def test_runtime_manifest_hashes(self):
        directory = ROOT / 'assets/art'
        manifest = json.loads((directory / 'runtime/asset_manifest.json').read_text())
        for name, entry in manifest['assets'].items():
            with self.subTest(asset=name):
                self.assertEqual(hashlib.sha256((directory / entry['source']).read_bytes()).hexdigest(), entry['source_sha256'])
                self.assertEqual(hashlib.sha256((directory / 'runtime' / entry['runtime']).read_bytes()).hexdigest(), entry['runtime_sha256'])


if __name__ == '__main__':
    unittest.main()
