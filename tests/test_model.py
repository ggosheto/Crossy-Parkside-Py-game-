import unittest
from parkside.config import CHARACTERS, COLS, START_ROW, STEP
from parkside.model import Game, World, Lane, Body, Terrain


def advance(game, seconds):
    for _ in range(round(seconds / STEP)):
        game.update(STEP)


class ModelTests(unittest.TestCase):
    def test_seeded_world_and_clear_resting_lanes(self):
        a, b = World(56), World(56)
        a.ensure(300)
        b.ensure(300)
        self.assertEqual(a.lanes, b.lanes)
        run = 0
        for row, lane in a.lanes.items():
            run = 0 if lane.kind == Terrain.GRASS else run + 1
            self.assertLessEqual(run, 4)
            if lane.kind == Terrain.GRASS:
                self.assertFalse(lane.trees & {4, 5, 6})
                self.assertFalse(lane.trees & lane.coins)
            if row % 6 == 0:
                self.assertEqual(lane.kind, Terrain.GRASS)

    def test_hop_uses_continuous_position_before_landing(self):
        g = Game(seed=6)
        x, row = g.px, g.row
        self.assertTrue(g.move("up"))
        self.assertEqual(g.row, row)
        advance(g, 0.075)
        self.assertGreater(g.visual_y, row)
        self.assertLess(g.visual_y, row + 1)
        self.assertEqual(g.score, 0)
        advance(g, 0.12)
        self.assertEqual(g.row, row + 1)
        self.assertEqual(g.score, 1)

    def test_one_buffered_hop_and_no_lateral_score_farming(self):
        g = Game(seed=6)
        g.move("right")
        g.move("right")
        g.move("left")
        advance(g, 0.4)
        self.assertAlmostEqual(g.px, 5.5)
        self.assertEqual(g.score, 0)

    def test_tree_and_boundary_block_do_not_reset_timer(self):
        g = Game(seed=6)
        g.lanes[3].trees.add(5)
        g.idle = 4
        self.assertFalse(g.move("up"))
        self.assertEqual(g.idle, 4)
        g.player.x = 0.5
        self.assertFalse(g.move("left"))

    def test_collect_only_when_landed_and_no_duplicate_coin(self):
        g = Game(seed=6)
        g.lanes[3].coins.add(5)
        g.move("up")
        advance(g, 0.1)
        self.assertEqual(g.coins_collected, 0)
        advance(g, 0.2)
        self.assertEqual(g.coins_collected, 1)
        advance(g, 0.1)
        self.assertEqual(g.coins_collected, 1)

    def test_road_collision_during_hop(self):
        g = Game(seed=6)
        g.lanes[3] = Lane(3, Terrain.ROAD, things=[Body(5, 1.5, (200, 100, 100), 5)])
        g.move("up")
        advance(g, 0.18)
        self.assertTrue(g.dead)
        self.assertEqual(g.lives, 0)

    def test_swept_collision_and_wrap_are_distinct(self):
        lane = Lane(6, Terrain.ROAD, things=[Body(6, 1, (0, 0, 0), 4.5)])
        self.assertTrue(lane.hits(5.5, True))
        self.assertFalse(lane.hits(5.5, False))
        lane.things[0].previous_x = -8
        self.assertFalse(lane.hits(5.5, True))

    def test_river_carrying_and_missing_log(self):
        g = Game(seed=6)
        g.player.row = 6
        g.best = 6
        g.lanes[6] = Lane(6, Terrain.RIVER, 1, 1, [Body(4, 3, (0, 0, 0), 4)])
        advance(g, 0.1)
        self.assertGreater(g.px, 5.5)
        self.assertFalse(g.dead)
        g.lanes[6].things = []
        g.update(STEP)
        self.assertTrue(g.dead)

    def test_checkpoint_recovers_after_pruning_without_repeated_damage(self):
        g = Game(CHARACTERS[1], seed=6)
        g.checkpoint = (5.5, 6)
        g.cam = 30
        g.player.row = 32
        g.world.ensure(60)
        g.lanes.pop(6, None)
        g.damage("traffic")
        self.assertEqual(g.row, 6)
        self.assertEqual(g.lives, 1)
        self.assertEqual(g.lanes[6].kind, Terrain.GRASS)
        self.assertGreater(g.player.invuln, 0)
        g.damage("again")
        self.assertEqual(g.lives, 1)
        self.assertIsNone(g.player.buffered)

    def test_idle_eagle_can_be_escaped_by_forward_progress(self):
        g = Game(seed=6)
        advance(g, 8.6)
        self.assertTrue(g.eagle_active)
        g.move("up")
        advance(g, 0.2)
        self.assertFalse(g.dead)
        self.assertFalse(g.eagle_active)
        advance(g, 10)
        self.assertTrue(g.dead)

    def test_pruning_bounds_long_run_memory(self):
        g = Game(seed=6)
        g.world.ensure(1020)
        g.cam = 1000
        g.player.row = 1002
        g.player.invuln = 20
        g.update(STEP)
        self.assertLess(len(g.lanes), 40)
        self.assertIn(g.checkpoint[1], g.lanes)

    def test_train_has_two_second_warning(self):
        g = Game(seed=6)
        l = Lane(8, Terrain.RAIL, timer=0.01)
        l.update(0.02, g.world.rng)
        self.assertEqual(l.phase, "warn")
        for _ in range(200):
            l.update(STEP, g.world.rng)
        self.assertEqual(l.phase, "warn")
        for _ in range(45):
            l.update(STEP, g.world.rng)
        self.assertEqual(l.phase, "pass")
        self.assertEqual(len(l.things), 1)

    def test_fx_rng_does_not_change_future_lanes(self):
        a, b = Game(seed=6), Game(seed=6)
        a.burst(True)
        a.world.ensure(80)
        b.world.ensure(80)
        self.assertEqual(a.lanes, b.lanes)


if __name__ == "__main__":
    unittest.main()
