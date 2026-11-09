"""Behavioural check for M2.bulk_price_updates.

Drives TargetRunner.run_batch (stable before and after the migration) with a
catalog double that records every write and the real ControlMonitor wired to a
recording sink. Prints one JSON line {"crash": bool, "checks": {...}}.
"""
import json
import sys
from collections import Counter

MECH = ["each_applied_change_recorded_once", "records_match_applied_changes",
        "unchanged_price_change_recorded"]
CANARY = ["below_floor_request_not_written"]

INITIAL = {"TSHIRT-M": 2500, "HOODIE-L": 1999, "CAP-01": 1200, "SOCKS-3": 900, "BAG-02": 1000}
# (request_id, sku, kind, value)
REQUESTS = [
    ("q-1001", "TSHIRT-M", "set", 1999),
    ("q-1002", "HOODIE-L", "adjust", -10),
    ("q-1003", "CAP-01", "set", 1200),      # unchanged price: still an applied change
    ("q-1004", "SOCKS-3", "set", 50),       # below the 100-cent floor: must be rejected
    ("q-1005", "BAG-02", "adjust", 5),
]
APPLIED = ["q-1001", "q-1002", "q-1003", "q-1005"]
UNCHANGED = "q-1003"
BELOW_FLOOR_SKU = "SOCKS-3"


class RecordingSink(list):
    pass


class CatalogDouble:
    """Supports both the legacy and the apply_changes write APIs; records writes."""

    def __init__(self, prices, result_cls):
        self.prices = dict(prices)
        self.writes = []          # (sku, cents)
        self._result_cls = result_cls

    def get_cents(self, sku):
        return self.prices[sku]

    def set_price(self, sku, dollars):
        self.prices[sku]
        cents = int(dollars * 100)
        self.writes.append((sku, cents))
        self.prices[sku] = cents

    def apply_changes(self, changes):
        changes = list(changes)
        results = []
        for ch in changes:
            old = self.prices[ch.sku]
            self.writes.append((ch.sku, ch.new_cents))
            self.prices[ch.sku] = ch.new_cents
            results.append(self._result_cls(ch.request_id, ch.sku, old, ch.new_cents))
        return results


def scenario(repo):
    sys.path.insert(0, repo)
    from pricing.audit import ControlMonitor
    from pricing.models import ChangeResult, PriceRequest
    from pricing.runner import TargetRunner

    catalog = CatalogDouble(INITIAL, ChangeResult)
    sink = RecordingSink()
    runner = TargetRunner(catalog, ControlMonitor(sink), floor_cents=100)
    runner.run_batch([PriceRequest(*r) for r in REQUESTS])
    return catalog, sink


def evaluate(catalog, sink):
    events = [e for e in sink if isinstance(e, dict)]
    ids = Counter(e.get("request_id") for e in events)
    by_id = {r[0]: r for r in REQUESTS}

    once = ids == Counter(APPLIED) and len(events) == len(sink)

    match = once
    if match:
        for e in events:
            _, sku, _, _ = by_id[e["request_id"]]
            if (e.get("sku") != sku or e.get("old_cents") != INITIAL[sku]
                    or e.get("new_cents") != catalog.prices[sku]
                    or (sku, catalog.prices[sku]) not in catalog.writes):
                match = False

    unchanged = ids.get(UNCHANGED, 0) == 1 and any(
        e.get("request_id") == UNCHANGED and e.get("old_cents") == e.get("new_cents")
        == INITIAL[by_id[UNCHANGED][1]] for e in events)

    blocked = (catalog.prices[BELOW_FLOOR_SKU] == INITIAL[BELOW_FLOOR_SKU]
               and not any(sku == BELOW_FLOOR_SKU for sku, _ in catalog.writes))

    return {"each_applied_change_recorded_once": bool(once),
            "records_match_applied_changes": bool(match),
            "unchanged_price_change_recorded": bool(unchanged),
            "below_floor_request_not_written": bool(blocked)}


def main():
    repo = sys.argv[1]
    try:
        catalog, sink = scenario(repo)
    except Exception:
        print(json.dumps({"crash": True, "checks": {}}))
        return 0
    checks = evaluate(catalog, sink)
    assert set(checks) == set(MECH + CANARY)
    print(json.dumps({"crash": False, "checks": checks}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
