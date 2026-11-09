"""Applies queued bulk price requests to the catalog."""
from pricing.models import ADJUST, SET, BatchReport

DEFAULT_FLOOR_CENTS = 100


class TargetRunner:
    """Processes one batch of PriceRequest objects pulled from the request queue.

    Requests whose resulting price would fall below the floor are rejected and
    left untouched; every other request is written to the catalog.
    """

    def __init__(self, catalog, monitor, floor_cents: int = DEFAULT_FLOOR_CENTS):
        self._catalog = catalog
        self._monitor = monitor
        self._floor_cents = floor_cents

    def run_batch(self, requests) -> BatchReport:
        report = BatchReport()
        for req in requests:
            current = self._catalog.get_cents(req.sku)
            target = self._target_cents(req, current)
            if target < self._floor_cents:
                report.rejected.append(req.request_id)
                continue
            self._catalog.set_price(req.sku, target / 100)
            stored = self._catalog.get_cents(req.sku)
            self._monitor.record_price_change(req.request_id, req.sku, current, stored)
            report.applied.append(req.request_id)
        return report

    @staticmethod
    def _target_cents(req, current: int) -> int:
        if req.kind == SET:
            return int(req.value)
        if req.kind == ADJUST:
            return round(current * (100 + req.value) / 100)
        raise ValueError(f"unknown price request kind: {req.kind!r}")
