import pytest

from rollout.bus import PUSH_REQUESTED, ROLLBACK_REQUESTED, EventBus
from rollout.external_requester import ExternalRequester
from rollout.formatting import summarize


def test_drain_publishes_by_kind():
    bus = EventBus()
    got = []
    bus.subscribe(PUSH_REQUESTED, lambda r: got.append(("push", r["request_id"])))
    bus.subscribe(ROLLBACK_REQUESTED, lambda r: got.append(("rollback", r["request_id"])))
    requester = ExternalRequester(bus)
    requester.enqueue({"kind": "push", "request_id": "a"})
    requester.enqueue({"kind": "rollback", "request_id": "b"})
    assert requester.drain() == 2
    assert got == [("push", "a"), ("rollback", "b")]
    assert requester.pending() == 0


def test_unknown_kind_is_refused():
    requester = ExternalRequester(EventBus(), [{"kind": "reboot", "request_id": "c"}])
    with pytest.raises(ValueError):
        requester.drain()


def test_summary_text():
    assert summarize("rollback", "dock", "3.0.0", 1) == "rollback dock -> v3.0 (1 device)"
