import pytest

from moderation.app import build_pipeline
from moderation.managed_client import UnknownAction
from moderation.metrics import QueueMetrics


class MemoryTransport:
    def __init__(self):
        self.posts = []

    def post(self, channel, message):
        self.posts.append((channel, message))


def make_store():
    return {
        "AR-1": {"report_id": "AR-1", "category": "spam", "priority": "low", "reporter": "u-17"},
        "AR-2": {"report_id": "AR-2", "category": "harassment", "priority": "normal",
                 "reporter": "u-23"},
        "AR-3": {"report_id": "AR-3", "category": "violent_threat", "priority": "high",
                 "reporter": "u-31"},
    }


def make_client(store, metrics=None):
    replies = []
    client = build_pipeline(store, MemoryTransport(),
                            lambda to, text: replies.append((to, text)), metrics=metrics)
    return client, replies


def test_close_spam_report_marks_it_closed():
    store = make_store()
    client, _ = make_client(store)
    assert client.handle({"report_id": "AR-1", "action": "close"}) == "closed"
    assert store["AR-1"]["status"] == "closed"


def test_close_replies_to_reporter():
    store = make_store()
    client, replies = make_client(store)
    client.handle({"report_id": "AR-2", "action": "close", "resolution": "content removed"})
    assert replies == [("u-23", "Thanks for your report AR-2. Our team has reviewed it: "
                                "content removed.")]


def test_escalate_then_close():
    store = make_store()
    client, replies = make_client(store)
    client.handle({"report_id": "AR-3", "action": "escalate", "escalation_id": "ESC-9"})
    assert client.handle({"report_id": "AR-3", "action": "close"}) == "closed"
    assert store["AR-3"]["escalation_id"] == "ESC-9"
    assert replies[0][0] == "u-31"


def test_drain_processes_whole_queue():
    store = make_store()
    metrics = QueueMetrics()
    client, _ = make_client(store, metrics)
    results = client.drain([
        {"report_id": "AR-1", "action": "close"},
        {"report_id": "AR-3", "action": "escalate", "escalation_id": "ESC-4"},
        {"report_id": "AR-2", "action": "close"},
        {"report_id": "AR-3", "action": "close"},
    ])
    assert results == ["closed", "escalated", "closed", "closed"]
    assert metrics.count("report.closed") == 3


def test_unknown_action_is_rejected():
    client, _ = make_client(make_store())
    with pytest.raises(UnknownAction):
        client.handle({"report_id": "AR-1", "action": "archive"})
