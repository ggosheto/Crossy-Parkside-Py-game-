import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import pygame
from parkside.config import CHARACTERS, FREE_CHARACTERS, DIRS, STEP
from parkside.model import Game, Lane, Terrain, Body, World
from parkside.storage import ScoreStore, Scores
from parkside.economy import Progression
from parkside.rendering import (
    VoxelCollector,
    face_eyes,
    rotate_point,
    model_voxels,
    ordered_model,
)
from parkside.ui import Arcade, State

BY_NAME = {c.name: c for c in CHARACTERS}


def advance(game, seconds):
    for _ in range(round(seconds / STEP)):
        game.update(STEP)


class CompanionTests(unittest.TestCase):
    def test_eyes_are_symmetric_on_one_face_plane(self):
        c = VoxelCollector()
        face_eyes(None, c, 0.5, -0.02, 0.75, glint=False)
        left, right = c.parts
        self.assertAlmostEqual(left.y, right.y)
        self.assertAlmostEqual(left.z, right.z)
        self.assertAlmostEqual((left.x + left.w / 2 + right.x + right.w / 2) / 2, 0.5)
        self.assertEqual(left.w, right.w)

    def test_front_rotates_toward_each_move_direction(self):
        for direction, (dx, dy) in DIRS.items():
            center = rotate_point(0.5, 0.5, direction)
            front = rotate_point(0.5, 0.1, direction)
            self.assertAlmostEqual(front[0] - center[0], dx * 0.4)
            self.assertAlmostEqual(front[1] - center[1], dy * 0.4)
            g = Game(seed=2)
            g.move(direction)
            self.assertEqual(g.player.facing, direction)

    def test_blocked_move_does_not_change_heading(self):
        g = Game(seed=2)
        g.player.x = 0.5
        g.player.facing = "up"
        self.assertFalse(g.move("left"))
        self.assertEqual(g.player.facing, "up")

    def test_all_models_have_complete_geometry_in_every_direction(self):
        for char in CHARACTERS:
            for direction in DIRS:
                parts = model_voxels(char, direction)
                self.assertTrue(parts)
                self.assertTrue(all(v.w > 0 and v.d > 0 and v.h > 0 for v in parts))
                self.assertCountEqual(parts, ordered_model(char, direction))

    def test_robot_faceplate_is_drawn_before_both_eyes(self):
        parts = ordered_model(BY_NAME["Robot"])
        visor = next(i for i, v in enumerate(parts) if v.color == (30, 57, 67))
        eyes = [
            i
            for i, v in enumerate(parts)
            if v.color == BY_NAME["Robot"].accent and abs(v.h - 0.07) < 0.001
        ]
        self.assertEqual(len(eyes), 2)
        self.assertTrue(all(i > visor for i in eyes))

    def test_fox_magnet_collects_nearby_coins_exactly_once(self):
        fox = Game(BY_NAME["Fox"], seed=2)
        fox.lanes[2].coins = {4, 7, 8}
        fox.lanes[3].coins = {5}
        fox.update(STEP)
        self.assertEqual(fox.coins_collected, 3)
        self.assertEqual(fox.lanes[2].coins, {8})
        fox.update(STEP)
        self.assertEqual(fox.coins_collected, 3)

    def test_penguin_can_cross_water_without_logs(self):
        for name in ["Penguin", "Chicken"]:
            g = Game(BY_NAME[name], seed=2)
            g.lanes[2] = Lane(2, Terrain.RIVER, 1, 1, [])
            g.update(STEP)
            self.assertEqual(g.dead, name == "Chicken")
            if name == "Penguin":
                self.assertGreater(g.px, 5.5)

    def test_shield_duration_cooldown_and_no_protection_from_water(self):
        g = Game(BY_NAME["Turtle"], seed=2)
        self.assertTrue(g.activate_ability())
        self.assertFalse(g.activate_ability())
        g.damage("traffic")
        self.assertFalse(g.dead)
        advance(g, 2.6)
        g.damage("traffic")
        self.assertTrue(g.dead)
        g = Game(BY_NAME["Turtle"], seed=2)
        g.activate_ability()
        g.damage("water", shieldable=False)
        self.assertTrue(g.dead)

    def test_shield_recharges_and_other_characters_have_no_active_shield(self):
        g = Game(BY_NAME["Turtle"], seed=2)
        g.activate_ability()
        # Keep the idle system active but make forward progress between cycles.
        advance(g, 6)
        g.move("up")
        advance(g, 0.2)
        advance(g, 5.9)
        self.assertFalse(g.dead)
        self.assertTrue(g.activate_ability())
        self.assertFalse(Game(BY_NAME["Fox"], seed=2).activate_ability())


class NewHazardTests(unittest.TestCase):
    def test_spikes_warn_before_activation_and_retract(self):
        g = Game(seed=2)
        l = Lane(2, Terrain.SPIKES, phase="safe", timer=0.05, hazard_cols={5})
        g.lanes[2] = l
        advance(g, 0.1)
        self.assertEqual(l.phase, "warn")
        self.assertFalse(g.dead)
        advance(g, 1.1)
        self.assertTrue(g.dead)
        l.update(1.3, g.world.rng)
        self.assertEqual(l.phase, "safe")

    def test_spike_safe_columns_and_turtle_shield(self):
        for name, col in [("Chicken", 4), ("Turtle", 5)]:
            g = Game(BY_NAME[name], seed=2)
            g.player.x = col + 0.5
            g.lanes[2] = Lane(
                2, Terrain.SPIKES, phase="active", timer=1, hazard_cols={5}
            )
            if name == "Turtle":
                g.activate_ability()
            g.update(STEP)
            self.assertFalse(g.dead)

    def test_rocks_are_blockers_and_coins_have_clear_access(self):
        g = Game(seed=2)
        g.lanes[3].rocks.add(5)
        self.assertFalse(g.move("up"))
        world = World(75)
        world.ensure(300)
        self.assertTrue(any(l.kind == Terrain.SPIKES for l in world.lanes.values()))
        self.assertTrue(
            any(b.variant == 2 for l in world.lanes.values() for b in l.things)
        )
        for l in world.lanes.values():
            if l.kind == Terrain.GRASS:
                self.assertFalse(l.rocks & {4, 5, 6})
                self.assertFalse(l.coins & (l.rocks | l.trees))
                if l.row > 4:
                    self.assertTrue(l.coins & {4, 5, 6})


class ProgressionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "scores.json"
        self.store = ScoreStore(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def test_previous_coins_migrate_to_wallet_once(self):
        self.path.write_text(json.dumps({"version": 2, "best": 52, "coins": 17}))
        p = Progression(self.store)
        self.assertEqual((p.stats.best, p.stats.wallet), (52, 17))
        self.assertEqual(p.stats.owned, set(FREE_CHARACTERS))
        self.assertEqual(p.buy("Fox"), "bought")
        reloaded = Progression(self.store)
        self.assertEqual(reloaded.stats.wallet, 5)
        self.assertEqual(reloaded.stats.coins, 17)
        self.assertIn("Fox", reloaded.stats.owned)

    def test_insufficient_and_repeat_purchases_never_spend_coins(self):
        p = Progression(self.store)
        self.assertEqual(p.buy("Fox"), "funds")
        p.deposit(20)
        self.assertEqual(p.buy("Fox"), "bought")
        self.assertEqual(p.stats.wallet, 8)
        self.assertEqual(p.buy("Fox"), "owned")
        self.assertEqual(p.stats.wallet, 8)
        self.assertEqual(p.buy("Unknown"), "unknown")

    def test_purchase_save_failure_rolls_back_wallet_and_unlock(self):
        p = Progression(self.store)
        p.deposit(20)
        with patch.object(self.store, "save", return_value=False):
            self.assertEqual(p.buy("Fox"), "save_error")
        self.assertEqual(p.stats.wallet, 20)
        self.assertNotIn("Fox", p.stats.owned)
        self.assertEqual(self.store.load().wallet, 20)

    def test_selected_owned_companion_reloads_and_locked_selection_is_rejected(self):
        p = Progression(self.store)
        self.assertFalse(p.select("Fox"))
        p.deposit(20)
        p.buy("Penguin")
        self.assertEqual(Progression(self.store).stats.selected, "Penguin")

    def test_negative_deposit_is_rejected(self):
        p = Progression(self.store)
        with self.assertRaises(ValueError):
            p.deposit(-4, best=12)
        self.assertEqual(p.stats.wallet, 0)


class ShopApplicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((1280, 800))

    @classmethod
    def tearDownClass(cls):
        pygame.quit()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "scores.json"
        self.a = Arcade(enable_audio=False, save_path=self.path)

    def tearDown(self):
        self.a.hand.close()
        self.temp.cleanup()

    def test_locked_start_opens_shop_and_buy_allows_start(self):
        a = self.a
        a.sel = 3
        a.start()
        self.assertEqual(a.state, State.SHOP)
        self.assertIsNone(a.game)
        a.progression.deposit(12)
        a.action("buy:3")
        a.start()
        self.assertEqual(a.game.char.name, "Fox")
        self.assertEqual(a.stats.wallet, 0)

    def test_shop_click_targets_and_gallery_page(self):
        a = self.a
        a.action("shop")
        a.draw()
        self.assertIn("buy:3", a.buttons)
        self.assertNotIn("start", a.buttons)
        a.mouse = (215, 686)
        a.click()
        self.assertNotIn("Fox", a.stats.owned)
        a.progression.deposit(12)
        a.click()
        self.assertIn("Fox", a.stats.owned)
        a.action("menu")
        a.draw()
        self.assertIn("select:3", a.buttons)

    def test_coins_bank_during_play_without_double_credit_on_finish(self):
        a = self.a
        a.start()
        a.game.coins_collected = 3
        a.update(STEP)
        self.assertEqual(a.stats.wallet, 3)
        self.assertEqual(ScoreStore(self.path).load().wallet, 3)
        a.finish()
        self.assertEqual(a.stats.wallet, 3)
        self.assertEqual(a.stats.coins, 3)
        a.action("menu")
        a.start()
        self.assertEqual(a.stats.wallet, 3)

    def test_shield_and_cooldown_freeze_when_paused(self):
        a = self.a
        a.progression.deposit(35)
        a.action("shop")
        a.action("buy:5")
        a.start()
        a.key(pygame.K_e)
        a.update(0.1)
        a.action("pause")
        before = a.game.shield_time, a.game.ability_cooldown
        a.update(2)
        self.assertEqual(before, (a.game.shield_time, a.game.ability_cooldown))

    def test_all_shop_cards_and_pages_render_without_error(self):
        a = self.a
        for i in range(6):
            a.sel = i
            a.draw()
        a.action("shop")
        a.draw()
        self.assertTrue(all(f"buy:{i}" in a.buttons for i in (3, 4, 5)))


if __name__ == "__main__":
    unittest.main()
