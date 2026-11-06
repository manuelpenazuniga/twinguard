from renewals.events import EventBus
from renewals.formatting import rx_label, summary_line
from renewals.team_updates import post_queue_summary


def test_bus_calls_handlers_in_order():
    bus, seen = EventBus(), []
    bus.subscribe("t", lambda **kw: seen.append(("a", kw["x"])))
    bus.subscribe("t", lambda **kw: seen.append(("b", kw["x"])))
    assert bus.publish("t", x=1) == 2
    assert seen == [("a", 1), ("b", 1)]


def test_unsubscribe():
    bus, seen = EventBus(), []
    handler = lambda **kw: seen.append(kw)  # noqa: E731
    bus.subscribe("t", handler)
    bus.unsubscribe("t", handler)
    assert bus.publish("t", x=1) == 0
    assert seen == []


def test_formatting():
    assert rx_label(" lisinopril ", "10 mg", 30) == "Lisinopril 10 mg x30"
    assert summary_line([{"status": "issued"}, {"status": "held"}]) == "2 renewals: 1 issued, 1 held"


def test_queue_summary_can_be_disabled():
    posted = []
    assert post_queue_summary([{"status": "issued"}], posted.append, enabled=False) is None
    assert posted == []
    assert post_queue_summary([{"status": "issued"}], posted.append) == "1 renewal: 1 issued, 0 held"
