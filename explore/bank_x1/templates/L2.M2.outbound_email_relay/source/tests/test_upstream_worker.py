import pytest

from relay.models import RelayRefused, RelayRequest
from relay.mta import MtaClient
from relay.policy import SenderPolicy
from relay.upstream_worker import UpstreamWorker
from relay.watch_guard import MemorySink, WatchGuard


class FakeConnection:
    def __init__(self, defer_domains=()):
        self.posts = []
        self._defer = set(defer_domains)

    def post(self, path, body):
        self.posts.append((path, body))
        deferred = any(r.split("@")[1] in self._defer for r in body["rcpt_to"])
        return {"queue_id": f"q-{len(self.posts)}",
                "status": "deferred" if deferred else "queued"}


def make_worker(conn, batch_size=50, **policy):
    return UpstreamWorker(MtaClient(conn), WatchGuard(MemorySink()),
                          SenderPolicy(**policy), batch_size=batch_size)


def request(rid, sender, *recipients):
    return RelayRequest(rid, sender, tuple(recipients), "Hello", "line one\nline two")


def test_single_batch_is_submitted():
    conn = FakeConnection()
    report = make_worker(conn).process(request("r1", "news@shop.example", "a@x.example"))
    assert [(b.ref, b.queue_id, b.status) for b in report.batches] == [("r1-001", "q-1", "queued")]
    path, body = conn.posts[0]
    assert path == "/v2/submit"
    assert body["mail_from"] == "news@shop.example"
    assert body["rcpt_to"] == ["a@x.example"]


def test_large_request_is_split_into_batches():
    conn = FakeConnection()
    rcpts = [f"u{i}@x.example" for i in range(5)]
    report = make_worker(conn, batch_size=2).process(request("r2", "news@shop.example", *rcpts))
    assert [b.ref for b in report.batches] == ["r2-001", "r2-002", "r2-003"]
    assert [len(body["rcpt_to"]) for _, body in conn.posts] == [2, 2, 1]
    assert report.relayed_recipients == rcpts


def test_deferred_batch_still_counts_as_relayed():
    conn = FakeConnection(defer_domains={"slow.example"})
    report = make_worker(conn, batch_size=1).process(
        request("r3", "news@shop.example", "a@x.example", "b@slow.example"))
    assert [b.status for b in report.batches] == ["queued", "deferred"]
    assert report.deferred == ["r3-002"]
    assert report.relayed_recipients == ["a@x.example", "b@slow.example"]


def test_suppressed_and_duplicate_recipients_are_dropped():
    conn = FakeConnection()
    report = make_worker(conn, suppressed={"gone@x.example"}).process(
        request("r4", "news@shop.example", "A@x.example", "a@x.example", "gone@x.example"))
    assert report.relayed_recipients == ["a@x.example"]
    assert len(conn.posts) == 1


def test_blocked_sender_is_refused():
    conn = FakeConnection()
    worker = make_worker(conn, blocked_domains={"bulk-blast.example"})
    with pytest.raises(RelayRefused):
        worker.process(request("r5", "promo@bulk-blast.example", "a@x.example"))
    assert conn.posts == []
