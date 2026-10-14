"""Pure Python simulation. No Pygame, camera, audio or filesystem dependencies."""

from dataclasses import dataclass, field
from enum import Enum
import math
import random
from .config import (
    COLS,
    ROWS,
    START_ROW,
    IDLE_LIMIT,
    DIRS,
    CHARACTERS,
    CAR_COLORS,
    Character,
)


class Terrain(str, Enum):
    GRASS = "grass"
    ROAD = "road"
    RIVER = "river"
    RAIL = "rail"
    SPIKES = "spikes"


@dataclass
class Body:
    x: float
    w: float
    color: tuple[int, int, int]
    previous_x: float | None = None
    variant: int = 0

    def __post_init__(self):
        if self.previous_x is None:
            self.previous_x = self.x


@dataclass
class Lane:
    row: int
    kind: Terrain
    direction: int = 1
    speed: float = 0.0
    things: list[Body] = field(default_factory=list)
    trees: set[int] = field(default_factory=set)
    coins: set[int] = field(default_factory=set)
    phase: str = "wait"
    timer: float = 4.0
    decorations: list[tuple[int, str]] = field(default_factory=list)
    rocks: set[int] = field(default_factory=set)
    hazard_cols: set[int] = field(default_factory=set)

    def __post_init__(self):
        if self.kind == Terrain.SPIKES and self.phase == "wait":
            self.phase = "safe"

    def hits(self, px, swept=False):
        for body in self.things:
            left, right = body.x, body.x + body.w
            if swept and abs(body.x - body.previous_x) < 2:
                left = min(left, body.previous_x)
                right = max(right, body.previous_x + body.w)
            if px + 0.22 > left and px - 0.22 < right:
                return True
        return False

    def log_under(self, px):
        return next(
            (b for b in self.things if b.x + 0.08 <= px <= b.x + b.w - 0.08), None
        )

    def update(self, dt, rng, slow=1.0):
        if self.kind in (Terrain.ROAD, Terrain.RIVER):
            k = slow if self.kind == Terrain.ROAD else 1.0
            span = COLS + 8
            for b in self.things:
                b.previous_x = b.x
                b.x += self.direction * self.speed * k * dt
                if b.x > COLS + 4:
                    b.x -= span
                    b.previous_x = b.x
                elif b.x + b.w < -4:
                    b.x += span
                    b.previous_x = b.x
        elif self.kind == Terrain.SPIKES:
            self.timer -= dt
            if self.timer <= 0:
                next_phase, duration = {
                    "safe": ("warn", 1.0),
                    "warn": ("active", 1.2),
                    "active": ("safe", 2.6),
                }[self.phase]
                self.phase = next_phase
                self.timer += duration
        elif self.kind == Terrain.RAIL:
            if self.phase == "pass":
                b = self.things[0]
                b.previous_x = b.x
                b.x += self.direction * 20 * dt
                if b.x > COLS + 5 or b.x + b.w < -5:
                    self.things.clear()
                    self.phase, self.timer = "wait", rng.uniform(4, 7)
            else:
                self.timer -= dt
                if self.timer <= 0:
                    if self.phase == "wait":
                        self.phase, self.timer = "warn", 2.0
                    else:
                        self.phase = "pass"
                        x = -17 if self.direction > 0 else COLS + 4
                        self.things = [Body(x, 13, (93, 123, 143), x)]


@dataclass
class Hop:
    x0: float
    y0: float
    x1: float
    y1: float
    progress: float = 0.0


@dataclass
class Player:
    x: float = COLS // 2 + 0.5
    row: int = START_ROW
    lives: int = 1
    invuln: float = 0.0
    hop: Hop | None = None
    buffered: str | None = None
    facing: str = "up"


@dataclass
class Particle:
    x: float
    y: float
    z: float
    vx: float
    vy: float
    vz: float
    size: float
    color: tuple[int, int, int]
    life: float
    total: float


@dataclass
class Popup:
    x: float
    y: float
    z: float
    text: str = "+1"
    life: float = 0.85


@dataclass(frozen=True)
class Event:
    kind: str
    value: int | str = 0


class World:
    """Seeded generation with resting lanes and a clear passage through vegetation."""

    def __init__(self, seed):
        self.rng = random.Random(seed)
        self.lanes = {}
        self.top = -1
        self.hazards = 0

    def ensure(self, row):
        while self.top < row:
            self.top += 1
            self.lanes[self.top] = self.generate(self.top)

    def generate(self, row):
        rng = self.rng
        level = min(8, row // 15)
        if row <= START_ROW + 2 or row % 6 == 0 or self.hazards >= 4:
            kind = Terrain.GRASS
        else:
            kind = rng.choices(
                [
                    Terrain.GRASS,
                    Terrain.ROAD,
                    Terrain.RIVER,
                    Terrain.RAIL,
                    Terrain.SPIKES,
                ],
                [3, 5, 3, 1, 2 if row >= 10 else 0],
            )[0]
        self.hazards = 0 if kind == Terrain.GRASS else self.hazards + 1
        lane = Lane(row, kind, rng.choice([-1, 1]), timer=rng.uniform(4, 7))
        if kind == Terrain.GRASS:
            if row > START_ROW + 2:
                lane.trees = {
                    x for x in range(COLS) if rng.random() < 0.19 and x not in (4, 5, 6)
                }
                lane.coins = {
                    x
                    for x in range(COLS)
                    if x not in lane.trees and rng.random() < 0.12
                }
                lane.rocks = {
                    x
                    for x in range(COLS)
                    if x not in lane.trees
                    and x not in (4, 5, 6)
                    and rng.random() < 0.09
                }
                lane.coins.difference_update(lane.rocks)
                lane.coins.add(rng.choice([4, 5, 6]))
            lane.decorations = [
                (x, rng.choice(["flower", "stone", "tuft"]))
                for x in range(COLS)
                if x not in lane.trees | lane.rocks and rng.random() < 0.35
            ]
        elif kind == Terrain.ROAD:
            lane.speed = rng.uniform(1.4, 2.1) + level * 0.13
            for i in range(3):
                x = i * (COLS + 8) / 3 - 4 + rng.uniform(-0.4, 0.4)
                truck = row >= 8 and rng.random() < 0.28
                lane.things.append(
                    Body(
                        x,
                        rng.uniform(2.1, 2.6) if truck else rng.uniform(1.35, 1.8),
                        rng.choice(CAR_COLORS),
                        x,
                        2 if truck else 0,
                    )
                )
        elif kind == Terrain.RIVER:
            lane.speed = rng.uniform(0.85, 1.35) + level * 0.07
            for i in range(4):
                x = i * (COLS + 8) / 4 - 4
                lane.things.append(Body(x, 3.4, (140, 104, 72), x))
        elif kind == Terrain.SPIKES:
            lane.phase, lane.timer = "safe", rng.uniform(1.4, 2.6)
            safe = rng.sample(range(COLS), 2)
            lane.hazard_cols = set(range(COLS)) - set(safe)
        return lane


class Game:
    """Authoritative session state. Animation targets never teleport collision state."""

    def __init__(self, char: Character = CHARACTERS[0], seed=None):
        self.char = char
        self.seed = seed if seed is not None else random.SystemRandom().randrange(2**31)
        self.world = World(self.seed)
        self.player = Player(lives=char.lives)
        self.best = START_ROW
        self.cam = 0.0
        self.idle = self.elapsed = 0.0
        self.dead, self.cause = False, ""
        self.coins_collected = 0
        self.checkpoint = (self.player.x, START_ROW)
        self.events: list[Event] = []
        self.particles: list[Particle] = []
        self.popups: list[Popup] = []
        self.shake_time = self.shake_intensity = 0.0
        self.eagle_active = False
        self.eagle_timer = 0.0
        self.shield_time = self.ability_cooldown = 0.0
        self.shield_feedback = 0.0
        self.world.ensure(ROWS + 8)
        # Effects use their own RNG, so visual randomness cannot change the level.
        self.fx_rng = random.Random(self.seed ^ 0x98AB)

    @property
    def lanes(self):
        return self.world.lanes

    @property
    def px(self):
        return self.player.x

    @property
    def row(self):
        return self.player.row

    @property
    def lives(self):
        return self.player.lives

    @property
    def score(self):
        return max(0, self.best - START_ROW)

    @property
    def hop_t(self):
        return self.player.hop.progress if self.player.hop else 1.0

    @property
    def visual_x(self):
        h = self.player.hop
        return h.x0 + (h.x1 - h.x0) * self.smooth(h.progress) if h else self.px

    @property
    def visual_y(self):
        h = self.player.hop
        return h.y0 + (h.y1 - h.y0) * self.smooth(h.progress) if h else float(self.row)

    @staticmethod
    def smooth(t):
        return t * t * (3 - 2 * t)

    def move(self, direction):
        if self.dead or direction not in DIRS:
            return False
        if self.player.hop:
            self.player.buffered = direction
            return False
        dc, dr = DIRS[direction]
        col = int(math.floor(self.px)) + dc
        row = self.row + dr
        if not 0 <= col < COLS or row < max(0, int(self.cam) - 1):
            return False
        self.world.ensure(row + ROWS)
        if col in self.lanes[row].trees | self.lanes[row].rocks:
            self.events.append(Event("blocked"))
            return False
        self.player.facing = direction
        self.player.hop = Hop(self.px, self.row, col + 0.5, row)
        self.events.append(Event("hop"))
        return True

    def burst(self, death=False):
        rng = self.fx_rng
        count = 28 if death else 7
        for _ in range(count):
            self.particles.append(
                Particle(
                    self.visual_x,
                    self.visual_y + 0.5,
                    0.15,
                    rng.uniform(-2, 2) if death else rng.uniform(-0.5, 0.5),
                    rng.uniform(-2, 2) if death else rng.uniform(-0.5, 0.5),
                    rng.uniform(2, 5) if death else rng.uniform(0.5, 1.3),
                    rng.uniform(0.08, 0.18),
                    (
                        rng.choice([self.char.color, self.char.accent, (251, 203, 100)])
                        if death
                        else (221, 225, 182)
                    ),
                    1.1 if death else 0.4,
                    1.1 if death else 0.4,
                )
            )

    def activate_ability(self):
        if self.dead or self.char.ability != "shield" or self.ability_cooldown > 0:
            return False
        self.shield_time = 2.5
        self.ability_cooldown = 12.0
        self.events.append(Event("ability"))
        return True

    def collect_coin(self, lane, col):
        if col not in lane.coins:
            return
        lane.coins.remove(col)
        self.coins_collected += 1
        self.popups.append(Popup(col + 0.5, lane.row + 0.5, 0.95))
        self.events.append(Event("coin", self.coins_collected))

    def damage(self, cause, shieldable=True):
        if self.dead or self.player.invuln > 0:
            return
        if shieldable and self.shield_time > 0:
            if self.shield_feedback <= 0:
                self.events.append(Event("shield_hit"))
                self.shield_feedback = 0.35
            return
        self.burst(True)
        self.player.lives -= 1
        self.shake_time, self.shake_intensity = 0.4, 7
        self.events.append(Event("damage"))
        self.player.hop = None
        self.player.buffered = None
        if self.lives <= 0:
            self.dead, self.cause = True, cause
            self.events.append(Event("death", cause))
        else:
            self.respawn()

    def respawn(self):
        x, row = self.checkpoint
        if row not in self.lanes or self.lanes[row].kind != Terrain.GRASS:
            # A checkpoint survives pruning as a guaranteed safe landing area.
            self.lanes[row] = Lane(row, Terrain.GRASS)
        self.lanes[row].trees.discard(int(x))
        self.lanes[row].rocks.discard(int(x))
        self.player.x, self.player.row = x, row
        self.player.hop = self.player.buffered = None
        self.player.invuln = 1.8
        self.cam = max(0.0, row - 2.8)
        self.idle = 0.0
        self.shield_time = 0.0
        self.eagle_active = False
        self.events.append(Event("respawn"))

    def update(self, dt):
        self.elapsed += dt
        self.shake_time = max(0, self.shake_time - dt)
        for p in self.particles:
            p.x += p.vx * dt
            p.y += p.vy * dt
            p.z += p.vz * dt
            p.vz -= 13 * dt
            p.life -= dt
            if p.z < 0.02:
                p.z = 0.02
                p.vz = abs(p.vz) * 0.28
        self.particles[:] = [p for p in self.particles if p.life > 0]
        for p in self.popups:
            p.z += dt * 0.9
            p.life -= dt
        self.popups[:] = [p for p in self.popups if p.life > 0]
        if self.dead:
            return
        self.world.ensure(int(self.cam) + ROWS + 8)
        for lane in self.lanes.values():
            lane.update(dt, self.world.rng, self.char.slow)
        self.player.invuln = max(0, self.player.invuln - dt)
        self.shield_time = max(0, self.shield_time - dt)
        self.ability_cooldown = max(0, self.ability_cooldown - dt)
        self.shield_feedback = max(0, self.shield_feedback - dt)
        self.idle += dt
        h = self.player.hop
        landed = False
        if h:
            h.progress = min(1.0, h.progress + dt / 0.18)
            if h.progress >= 1:
                self.player.x, self.player.row = h.x1, int(h.y1)
                self.player.hop = None
                landed = True
                self.burst()
                if self.row > self.best:
                    self.best = self.row
                    self.idle = 0.0
                    self.eagle_active = False
                    self.events.append(Event("score", self.score))
                if self.lanes[self.row].kind == Terrain.GRASS:
                    self.checkpoint = self.px, self.row
        lane_row = int(math.floor(self.visual_y + 0.5))
        lane = self.lanes[lane_row]
        near_center = abs(self.visual_y - lane_row) <= 0.34
        if (
            lane.kind in (Terrain.ROAD, Terrain.RAIL)
            and near_center
            and lane.hits(self.visual_x, swept=True)
        ):
            self.damage(
                "Traffic caught you."
                if lane.kind == Terrain.ROAD
                else "The train arrived first."
            )
        elif (
            lane.kind == Terrain.SPIKES
            and lane.phase == "active"
            and near_center
            and int(self.visual_x) in lane.hazard_cols
        ):
            self.damage("The spikes caught you. Wait for the green light!")
        elif not self.player.hop and lane.kind == Terrain.RIVER:
            log = lane.log_under(self.px)
            if not log and self.char.ability != "swim":
                self.damage("You missed the floating log.", shieldable=False)
            else:
                self.player.x += (
                    lane.direction * lane.speed * dt * (1.0 if log else 0.35)
                )
                if self.px < 0.15 or self.px > COLS - 0.15:
                    self.damage("The current carried you away.", shieldable=False)
        if self.dead:
            return
        if not self.player.hop:
            current = self.lanes[self.row]
            col = int(self.px)
            self.collect_coin(current, col)
            if self.char.ability == "magnet":
                for near_row in range(self.row - 2, self.row + 3):
                    nearby = self.lanes.get(near_row)
                    if nearby:
                        for coin in list(nearby.coins):
                            if (
                                math.hypot(coin + 0.5 - self.px, near_row - self.row)
                                <= 2.0
                            ):
                                self.collect_coin(nearby, coin)
        if self.idle >= IDLE_LIMIT and not self.eagle_active:
            self.eagle_active, self.eagle_timer = True, 1.25
            self.events.append(Event("eagle"))
        if self.eagle_active:
            self.eagle_timer -= dt
            if self.eagle_timer <= 0:
                self.damage(
                    "The eagle caught up. Keep moving forward!", shieldable=False
                )
        target = max(0.0, self.row - 2.8)
        self.cam += max(0.0, target - self.cam) * (1 - math.exp(-5 * dt))
        floor = int(self.cam) - 4
        for old in list(self.lanes):
            if old < floor and old != self.checkpoint[1]:
                del self.lanes[old]
        if landed and self.player.buffered:
            pending, self.player.buffered = self.player.buffered, None
            self.move(pending)

    def drain_events(self):
        events, self.events = self.events, []
        return events
