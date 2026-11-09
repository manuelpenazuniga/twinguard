"""Clearance markdown job, already migrated to PriceCatalog.apply_changes.

Pattern for moving a writer off the deprecated ``set_price``: compute the new
price in integer cents, collect PriceChange objects, submit them in a single
``apply_changes`` call and build the report from the returned ChangeResult list.
"""
from pricing.models import BatchReport, PriceChange


class ClearanceJob:
    def __init__(self, catalog, markdown_pct: int = 30):
        self._catalog = catalog
        self._markdown_pct = markdown_pct

    def run(self, skus) -> BatchReport:
        report = BatchReport()
        changes = []
        for sku in skus:
            current = self._catalog.get_cents(sku)
            new_cents = round(current * (100 - self._markdown_pct) / 100)
            changes.append(PriceChange(f"clearance-{sku}", sku, new_cents))
        for result in self._catalog.apply_changes(changes):
            report.applied.append(result.request_id)
        return report
