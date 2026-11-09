from stockops.formatting import format_money, format_quantity
from stockops.ledger import StockItem, StockLedger
from stockops.pipeline import build_pipeline, run_queue


class RecordingSink:
    def __init__(self):
        self.deliveries = []

    def deliver(self, channel, alert):
        self.deliveries.append((channel, alert))


def make_ledger():
    return StockLedger([
        StockItem("KB-100", 40, 23.0),
        StockItem("MN-270", 25, 92.0),
    ])


def run(requests, threshold=500.0):
    ledger, sink, review_log = make_ledger(), RecordingSink(), []
    bus = build_pipeline(ledger, sink, threshold, review_log)
    run_queue(bus, requests)
    return ledger, sink, review_log


def req(request_id, kind, sku, quantity):
    return {"request_id": request_id, "kind": kind, "sku": sku,
            "quantity": quantity, "submitted_by": "queue-7"}


def test_recount_gain_updates_on_hand():
    ledger, _, review_log = run([req("A-1", "recount_gain", "KB-100", 3)])
    assert ledger.on_hand("KB-100") == 43
    assert review_log == [{"request_id": "A-1", "severity": "notice", "reason": None}]


def test_small_write_off_is_a_notice_without_alerts():
    ledger, sink, review_log = run([req("A-2", "write_off", "KB-100", 4)])
    assert ledger.on_hand("KB-100") == 36
    assert review_log[0]["severity"] == "notice"
    assert sink.deliveries == []


def test_large_write_off_is_classified_critical():
    ledger, _, review_log = run([req("A-3", "write_off", "MN-270", 20)])
    assert ledger.on_hand("MN-270") == 5
    assert review_log[0]["severity"] == "critical"


def test_rejected_request_does_not_stop_the_queue():
    ledger, _, review_log = run([
        req("A-4", "write_off", "XX-404", 2),
        req("A-5", "recount_gain", "KB-100", 1),
    ])
    assert [e["severity"] for e in review_log] == ["rejected", "notice"]
    assert review_log[0]["reason"] == "unknown_sku"
    assert ledger.on_hand("KB-100") == 41


def test_write_off_beyond_stock_is_rejected():
    ledger, _, review_log = run([req("A-6", "write_off", "KB-100", 99)])
    assert ledger.on_hand("KB-100") == 40
    assert review_log[0]["reason"] == "insufficient_stock"


def test_formatting_helpers():
    assert format_money(1840) == "EUR 1,840.00"
    assert format_quantity(1) == "1 unit"
    assert format_quantity(20) == "20 units"
