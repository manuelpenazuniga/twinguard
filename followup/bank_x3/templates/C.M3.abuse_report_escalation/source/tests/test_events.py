from moderation.events import EventBus
from moderation.metrics import QueueMetrics


def test_handlers_run_in_order_and_wildcard_last():
    bus = EventBus()
    seen = []
    bus.subscribe("*", lambda e: seen.append(("any", e.name)))
    bus.subscribe("report.closed", lambda e: seen.append(("first", e.payload["report_id"])))
    bus.subscribe("report.closed", lambda e: seen.append(("second", e.payload["report_id"])))
    bus.publish("report.closed", {"report_id": "AR-5"})
    assert seen == [("first", "AR-5"), ("second", "AR-5"), ("any", "report.closed")]


def test_unsubscribe():
    bus = EventBus()
    seen = []
    handler = bus.subscribe("report.escalated", seen.append)
    bus.unsubscribe("report.escalated", handler)
    bus.publish("report.escalated", {})
    assert seen == []


def test_metrics_count_by_category():
    bus = EventBus()
    metrics = QueueMetrics()
    bus.subscribe("*", metrics.record)
    bus.publish("report.closed", {"category": "spam"})
    bus.publish("report.closed", {"category": "spam"})
    bus.publish("report.escalated", {"category": "doxxing"})
    assert metrics.snapshot() == {"report.closed": 2, "report.escalated": 1}
    assert metrics.by_category("report.closed") == {"spam": 2}
