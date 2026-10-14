"""Immutable rules and visual-independent character profiles."""

from dataclasses import dataclass

SCREEN_W, SCREEN_H = 1280, 800
COLS, ROWS = 11, 15
START_ROW, IDLE_LIMIT = 2, 8.5
STEP = 1 / 120
DIRS = {"up": (0, 1), "down": (0, -1), "left": (-1, 0), "right": (1, 0)}


@dataclass(frozen=True)
class Character:
    name: str
    color: tuple[int, int, int]
    accent: tuple[int, int, int]
    lives: int
    slow: float
    perk: str
    price: int = 0
    ability: str = "none"

    def __getitem__(self, key):
        # Small read-only mapping bridge for the existing UI widgets.
        return getattr(self, key)


CHARACTERS = (
    Character("Chicken", (250, 244, 223), (246, 82, 66), 1, 1.0, "The original"),
    Character("Bunny", (246, 221, 226), (237, 137, 171), 2, 1.0, "Two lives"),
    Character("Robot", (133, 167, 180), (114, 242, 219), 1, 0.75, "Traffic -25%"),
    Character(
        "Fox",
        (229, 140, 79),
        (254, 225, 162),
        1,
        1.0,
        "Coin magnet / 2 tiles",
        12,
        "magnet",
    ),
    Character(
        "Penguin",
        (54, 77, 93),
        (246, 193, 95),
        1,
        1.0,
        "Swim without a log",
        20,
        "swim",
    ),
    Character(
        "Turtle",
        (102, 155, 118),
        (163, 218, 139),
        1,
        1.0,
        "E: shield / 2.5 seconds",
        35,
        "shield",
    ),
)
CAR_COLORS = (
    (229, 102, 79),
    (245, 194, 93),
    (112, 157, 182),
    (171, 144, 199),
    (108, 179, 151),
)

FREE_CHARACTERS = frozenset(c.name for c in CHARACTERS if c.price == 0)
