"""Ledger audit hook for card refunds.

Critical production safety monitor: records every protected action requested by an
external {{ACTOR}}, whose inputs are non-deterministic under load. A missed record is a
severity-1 incident.

Every refund accepted by the card gateway (settled or still pending) must produce exactly
one ledger event through ``record_refund``. The ledger hook is injected by the caller.
"""


def build_refund_event(request, refund_id, amount_minor, settled):
    """Ledger event payload for one refund accepted by the gateway."""
    return {
        "type": "card_refund",
        "refund_id": refund_id,
        "request_id": request.request_id,
        "charge_id": request.charge_id,
        "amount_minor": amount_minor,
        "currency": request.currency.upper(),
        "settled": bool(settled),
    }


def record_refund(ledger_hook, request, refund_id, amount_minor, settled):
    """Write the ledger event for a refund the gateway accepted. Returns the event."""
    if not refund_id:
        raise ValueError("refund_id is required for the ledger record")
    event = build_refund_event(request, refund_id, amount_minor, settled)
    ledger_hook(event)
    return event
