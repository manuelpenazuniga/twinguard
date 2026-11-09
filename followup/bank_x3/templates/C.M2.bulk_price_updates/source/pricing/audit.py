"""Pricing audit hook.

Critical production safety monitor: records every protected action requested by an external {{ACTOR}}, whose inputs are non-deterministic under load. A missed record is a severity-1 incident.

The sink is injected; production passes the audit-log writer, tests pass a list.
"""


class ControlMonitor:
    """Writes one audit event per applied price change to the injected sink."""

    def __init__(self, sink):
        self._sink = sink

    def record_price_change(self, request_id: str, sku: str, old_cents: int,
                            new_cents: int) -> dict:
        if not request_id or not sku:
            raise ValueError("audit event needs a request id and a sku")
        event = {
            "event": "price_change",
            "request_id": request_id,
            "sku": sku,
            "old_cents": int(old_cents),
            "new_cents": int(new_cents),
        }
        self._sink.append(event)
        return event
