"""In-memory price catalog used by the pricing jobs and their tests.

Production wires a client with the same interface against the catalog service.
Two write APIs exist while callers are being moved over:

* ``set_price(sku, dollars)``: legacy, takes a float amount in dollars. Deprecated.
* ``apply_changes(changes)``: takes PriceChange objects in integer cents and
  returns one ChangeResult per change, in the same order.
"""
from pricing.models import ChangeResult, PriceChange


class PriceCatalog:
    def __init__(self, prices=None):
        self._prices = dict(prices or {})

    def get_cents(self, sku: str) -> int:
        try:
            return self._prices[sku]
        except KeyError:
            raise KeyError(f"unknown sku: {sku}") from None

    def set_price(self, sku: str, dollars: float) -> None:
        """Deprecated: use apply_changes."""
        self.get_cents(sku)
        self._prices[sku] = int(dollars * 100)

    def apply_changes(self, changes: list[PriceChange]) -> list[ChangeResult]:
        for change in changes:
            self.get_cents(change.sku)
            if not isinstance(change.new_cents, int) or change.new_cents < 0:
                raise ValueError(f"invalid price for {change.sku}: {change.new_cents!r}")
        results = []
        for change in changes:
            old = self._prices[change.sku]
            self._prices[change.sku] = change.new_cents
            results.append(ChangeResult(change.request_id, change.sku, old, change.new_cents))
        return results

    def snapshot(self) -> dict:
        return dict(self._prices)
