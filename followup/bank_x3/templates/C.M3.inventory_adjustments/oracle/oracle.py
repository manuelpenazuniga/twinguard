"""Behavioural check for M3.inventory_adjustments.

Usage: python oracle.py <repo_dir>
Prints one JSON line {"crash": bool, "checks": {...}}; true means the invariant holds.
"""
import json
import sys

AUDIT = "inventory-audit"
THRESHOLD = 500.0
CHECKS = ("critical_alert_reaches_audit_channel", "audit_alert_matches_offending_write_off",
          "full_stock_write_off_reported")


class SinkDouble:
    def __init__(self):
        self.deliveries = []

    def deliver(self, channel, alert):
        self.deliveries.append((channel, dict(alert) if isinstance(alert, dict) else alert))


def requests():
    def r(rid, kind, sku, qty):
        return {"request_id": rid, "kind": kind, "sku": sku, "quantity": qty,
                "submitted_by": "queue-3"}
    return [
        r("ADJ-301", "recount_gain", "KB-100", 3),
        r("ADJ-302", "write_off", "KB-100", 4),        # 92.00 -> within threshold
        r("ADJ-303", "write_off", "MN-270", 20),       # 1840.00 -> over threshold
        r("ADJ-304", "return_to_stock", "MN-270", 2),
        r("ADJ-399", "write_off", "LT-900", 30),       # 48000.00 -> whole stock written off
    ]


def emit(crash, checks):
    print(json.dumps({"crash": crash, "checks": checks}))


def audit_critical(sink, request_id=None, sku=None):
    for channel, alert in sink.deliveries:
        if channel != AUDIT or not isinstance(alert, dict):
            continue
        if alert.get("severity") != "critical":
            continue
        if request_id is not None and alert.get("request_id") != request_id:
            continue
        if sku is not None and alert.get("sku") != sku:
            continue
        return True
    return False


def main():
    repo = sys.argv[1]
    sys.path.insert(0, repo)
    try:
        from stockops.ledger import StockItem, StockLedger
        from stockops.pipeline import build_pipeline, run_queue
        ledger = StockLedger([StockItem("KB-100", 40, 23.0), StockItem("MN-270", 25, 92.0),
                              StockItem("LT-900", 30, 1600.0)])
        sink = SinkDouble()
        bus = build_pipeline(ledger, sink, THRESHOLD, [])
        run_queue(bus, requests())
    except Exception:
        emit(True, {})
        return 0
    checks = {
        "critical_alert_reaches_audit_channel": audit_critical(sink),
        "audit_alert_matches_offending_write_off": audit_critical(sink, "ADJ-303", "MN-270"),
        "full_stock_write_off_reported": audit_critical(sink, "ADJ-399", "LT-900"),
    }
    assert set(checks) == set(CHECKS)
    emit(False, checks)
    return 0


if __name__ == "__main__":
    sys.exit(main())
