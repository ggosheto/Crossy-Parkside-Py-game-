import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
import json
from pathlib import Path
import tempfile
import unittest
import pygame
from parkside.config import CHARACTERS, SCREEN_W, SCREEN_H
from parkside.model import Game
from parkside.storage import ScoreStore, Scores
from parkside.ui import Arcade, State, pointer, viewport


class ApplicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((SCREEN_W, SCREEN_H))

    @classmethod
    def tearDownClass(cls):
        pygame.quit()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "score.json"
        self.app = Arcade(enable_audio=False, save_path=self.path)

    def tearDown(self):
        self.app.hand.close()
        self.temp.cleanup()

    def test_menu_mouse_selection_and_start(self):
        a = self.app
        a.draw()
        a.mouse = (600, 650)
        a.click()
        self.assertEqual(a.sel, 1)
        a.key(pygame.K_RETURN)
        self.assertEqual(a.state, State.PLAY)
        self.assertEqual(a.game.lives, 2)

    def test_pause_freezes_simulation_and_blocks_underlying_controls(self):
        a = self.app
        a.start()
        a.update(0.1)
        a.action("pause")
        a.draw()
        self.assertEqual(set(a.buttons), {"resume", "menu"})
        idle = a.game.idle
        positions = [b.x for l in a.game.lanes.values() for b in l.things]
        a.update(1)
        self.assertEqual(a.game.idle, idle)
        self.assertEqual(
            positions, [b.x for l in a.game.lanes.values() for b in l.things]
        )
        a.key(pygame.K_ESCAPE)
        self.assertEqual(a.state, State.PLAY)

    def test_fixed_step_is_independent_of_render_frame_rate(self):
        a = self.app
        b = Arcade(enable_audio=False, save_path=self.path)
        for app in (a, b):
            app.start()
            app.game = Game(seed=42)
        for _ in range(120):
            a.update(1 / 60)
        for _ in range(60):
            b.update(1 / 30)
        self.assertAlmostEqual(a.game.elapsed, b.game.elapsed, places=8)
        self.assertEqual(a.game.lanes, b.game.lanes)

    def test_scores_persist_and_results_do_not_accumulate_darkness(self):
        a = self.app
        a.start()
        a.game.best = 12
        a.game.coins_collected = 3
        a.game.cause = "Traffic caught you."
        a.finish()
        a.state_time = 1
        self.assertEqual(json.loads(self.path.read_text())["best"], 10)
        a.draw()
        first = pygame.image.tobytes(a.surface, "RGB")
        a.draw()
        self.assertEqual(first, pygame.image.tobytes(a.surface, "RGB"))
        self.assertEqual(ScoreStore(self.path).load(), Scores(10, 3, wallet=3))
        a.key(pygame.K_r)
        self.assertEqual(a.game.score, 0)

    def test_letterbox_pointer_and_render_all_sizes(self):
        a = self.app
        a.draw()
        for size in [(640, 400), (900, 900), (1600, 900), (400, 800)]:
            v = viewport(size)
            center = pointer(v.center, size)
            self.assertAlmostEqual(center[0], 640, delta=2)
            self.assertAlmostEqual(center[1], 400, delta=2)
            self.assertLessEqual(v.w, size[0])
            self.assertLessEqual(v.h, size[1])
            pygame.transform.smoothscale(a.surface, v.size)
        self.assertEqual(pointer((0, 0), (400, 800)), (-100, -100))

    def test_corrupt_storage_falls_back_and_atomic_versioned_save(self):
        self.path.write_text("garbage")
        store = ScoreStore(self.path)
        self.assertEqual(store.load(), Scores())
        self.assertTrue(store.save(Scores(34, 5)))
        self.assertEqual(store.load(), Scores(34, 5))
        self.assertFalse(self.path.with_suffix(".tmp").exists())

    def test_key_hold_release_and_pause_clear(self):
        a = self.app
        a.start()
        a.key(pygame.K_w)
        a.update(0.2)
        self.assertEqual(a.game.score, 1)
        a.release(pygame.K_w)
        self.assertIsNone(a.held)
        a.action("pause")
        a.action("resume")
        self.assertIsNone(a.held)


if __name__ == "__main__":
    unittest.main()
