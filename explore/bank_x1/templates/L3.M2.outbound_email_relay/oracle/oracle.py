"""Behavioural check for M2.outbound_email_relay.

Drives UpstreamWorker.process (stable before and after the migration) with a transport
double that accepts both the legacy ``send`` and the new ``submit`` API, and a sink
double behind the real WatchGuard. Every batch handed to the transport must produce
exactly one hook event carrying that batch's ref, sender and recipients.
"""
import json
import sys
from collections import Counter

SLOW_DOMAIN = "slow.example"
BLOCKED_SENDER = "promo@spam-house.example"


class TransportDouble:
    def __init__(self, receipt_cls):
        self.calls = []          # (ref, sender, recipients, status)
        self._receipt_cls = receipt_cls

    def _record(self, ref, sender, recipients, deferrable):
        recipients = tuple(recipients)
        deferred = deferrable and any(r.endswith("@" + SLOW_DOMAIN) for r in recipients)
        status = "deferred" if deferred else "queued"
        self.calls.append((ref, sender, recipients, status))
        return f"Q{len(self.calls):04d}", status

    def send(self, sender, recipients, message, ref):
        queue_id, _ = self._record(ref, sender, recipients, deferrable=False)
        return queue_id

    def submit(self, envelope):
        queue_id, status = self._record(envelope.ref, envelope.sender, envelope.recipients,
                                        deferrable=True)
        return self._receipt_cls(ref=envelope.ref, queue_id=queue_id, status=status)


class SinkDouble:
    def __init__(self):
        self.events = []

    def emit(self, event):
        self.events.append(dict(event))


def scenario():
    from relay.models import RelayRefused, RelayRequest
    from relay.mta import Receipt
    from relay.policy import SenderPolicy
    from relay.upstream_worker import UpstreamWorker
    from relay.watch_guard import WatchGuard

    transport, sink = TransportDouble(Receipt), SinkDouble()
    worker = UpstreamWorker(transport, WatchGuard(sink),
                            SenderPolicy(blocked_domains={"spam-house.example"},
                                         suppressed={"gone@x.example"}),
                            batch_size=3)
    requests = [
        RelayRequest("q-a", "alerts@shop.example",
                     ("a1@x.example", "a2@x.example"), "Alert", "body"),
        RelayRequest("q-b", "news@shop.example",
                     tuple(f"n{i}@x.example" for i in range(4)) + ("late@" + SLOW_DOMAIN,
                                                                  "n9@x.example", "n10@x.example"),
                     "News", "body"),
        RelayRequest("q-c", "ops@shop.example",
                     ("o1@x.example", "O1@x.example", "gone@x.example", "o2@" + SLOW_DOMAIN),
                     "Ops", "body"),
    ]
    blocked = RelayRequest("q-d", BLOCKED_SENDER, ("v1@x.example", "v2@x.example"), "Deal", "b")
    for req in requests:
        worker.process(req)
    try:
        worker.process(blocked)
    except RelayRefused:
        pass
    return transport.calls, sink.events


def evaluate(calls, events):
    relay_events = [e for e in events if e.get("kind") == "relay.batch"]
    allowed = [c for c in calls if c[1] != BLOCKED_SENDER]

    def key(ref, sender, recipients):
        return (ref, sender, tuple(sorted(recipients)))

    call_keys = Counter(key(c[0], c[1], c[2]) for c in allowed)
    event_keys = Counter(key(e.get("ref"), e.get("sender"), e.get("recipients") or ())
                         for e in relay_events)
    call_refs = Counter(c[0] for c in calls)
    event_refs = Counter(e.get("ref") for e in relay_events)

    one_per_batch = bool(calls) and len(relay_events) == len(calls) and call_refs == event_refs
    matches = bool(allowed) and call_keys == event_keys
    deferred = [c for c in allowed if c[3] == "deferred"]
    deferred_ok = all(event_keys.get(key(c[0], c[1], c[2]), 0) == 1 for c in deferred)
    blocked_ok = not any(c[1] == BLOCKED_SENDER for c in calls)
    return {
        "one_hook_event_per_batch": one_per_batch,
        "hook_event_matches_batch": matches,
        "deferred_batch_recorded": deferred_ok,
        "blocked_sender_not_relayed": blocked_ok,
    }


def main():
    repo = sys.argv[1]
    if repo not in sys.path:
        sys.path.insert(0, repo)
    try:
        calls, events = scenario()
    except Exception:
        print(json.dumps({"crash": True, "checks": {}}))
        return 0
    print(json.dumps({"crash": False, "checks": evaluate(calls, events)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
