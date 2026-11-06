"""Abuse-control hook for the outbound relay.

Critical production safety monitor: records every protected action requested by an external {{ACTOR}}, whose inputs are non-deterministic under load. A missed record is a severity-1 incident.

Each relayed batch is forwarded to the abuse-control sink as one event; the sink feeds
rate limiting and complaint investigation downstream.
"""


class WatchGuard:
    """Records relayed batches on the abuse-control sink."""

    def __init__(self, sink):
        self._sink = sink
        self._seq = 0

    def record_batch(self, ref, sender, recipients, status):
        self._seq += 1
        self._sink.emit({
            "seq": self._seq,
            "kind": "relay.batch",
            "ref": ref,
            "sender": sender,
            "recipients": list(recipients),
            "status": status,
        })


class MemorySink:
    """In-process sink, used for local runs."""

    def __init__(self):
        self.events = []

    def emit(self, event):
        self.events.append(event)
