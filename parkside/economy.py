"""Local in-game currency. Purchases are committed only after successful saving."""

from dataclasses import replace
from .config import CHARACTERS


class Progression:
    def __init__(self, store):
        self.store = store
        self.stats = store.load()

    def deposit(self, amount, best=0):
        if amount < 0:
            raise ValueError("A deposit cannot be negative")
        if amount <= 0 and best <= self.stats.best:
            return True
        candidate = replace(
            self.stats,
            best=max(self.stats.best, best),
            coins=self.stats.coins + amount,
            wallet=self.stats.wallet + amount,
        )
        if not self.store.save(candidate):
            return False
        self.stats = candidate
        return True

    def buy(self, name):
        char = next((c for c in CHARACTERS if c.name == name), None)
        if char is None:
            return "unknown"
        if name in self.stats.owned:
            return "owned"
        if self.stats.wallet < char.price:
            return "funds"
        candidate = replace(
            self.stats,
            wallet=self.stats.wallet - char.price,
            owned=self.stats.owned | {name},
            selected=name,
        )
        if not self.store.save(candidate):
            return "save_error"
        self.stats = candidate
        return "bought"

    def select(self, name):
        if name not in self.stats.owned:
            return False
        candidate = replace(self.stats, selected=name)
        if not self.store.save(candidate):
            return False
        self.stats = candidate
        return True
