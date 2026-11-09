"""In-memory stock ledger used by the adjustment pipeline."""
from dataclasses import dataclass


@dataclass
class StockItem:
    sku: str
    on_hand: int
    unit_cost: float


class StockLedger:
    """Keeps on-hand quantities and the list of posted movements."""

    def __init__(self, items=()):
        self._items = {item.sku: item for item in items}
        self.movements = []

    def get(self, sku):
        return self._items.get(sku)

    def on_hand(self, sku):
        return self._items[sku].on_hand

    def post(self, sku, delta, reference):
        item = self._items[sku]
        if item.on_hand + delta < 0:
            raise ValueError(f"{sku}: movement {delta} would make stock negative")
        item.on_hand += delta
        self.movements.append((reference, sku, delta))
        return item.on_hand
