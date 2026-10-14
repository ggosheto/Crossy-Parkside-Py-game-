"""Versioned, atomic progression storage and migration of existing scores."""

from dataclasses import dataclass, field
from pathlib import Path
import json
from .config import CHARACTERS, FREE_CHARACTERS


@dataclass
class Scores:
    best: int = 0
    coins: int = 0  # Lifetime earnings; purchases never reduce this statistic.
    wallet: int = 0
    owned: set[str] = field(default_factory=lambda: set(FREE_CHARACTERS))
    selected: str = "Chicken"


class ScoreStore:
    def __init__(self, path=None):
        self.path = Path(path) if path else Path.home() / ".crossy_neon" / "scores.json"

    def load(self):
        try:
            data = json.loads(self.path.read_text())
            coins = max(0, int(data.get("coins", 0)))
            # Old editions had no spending: all old earnings become available coins.
            wallet = max(0, int(data.get("wallet", coins)))
            known = {c.name for c in CHARACTERS}
            raw_owned = data.get("owned", [])
            owned = set(FREE_CHARACTERS) | (
                {n for n in raw_owned if isinstance(n, str) and n in known}
                if isinstance(raw_owned, list)
                else set()
            )
            selected = data.get("selected", "Chicken")
            if selected not in owned:
                selected = "Chicken"
            return Scores(
                max(0, int(data.get("best", 0))), coins, wallet, owned, selected
            )
        except (OSError, ValueError, TypeError, AttributeError):
            return Scores()

    def save(self, scores):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp = self.path.with_suffix(".tmp")
            temp.write_text(
                json.dumps(
                    {
                        "version": 3,
                        "best": scores.best,
                        "coins": scores.coins,
                        "wallet": scores.wallet,
                        "owned": sorted(scores.owned),
                        "selected": scores.selected,
                    }
                )
            )
            temp.replace(self.path)
            return True
        except OSError:
            return False
