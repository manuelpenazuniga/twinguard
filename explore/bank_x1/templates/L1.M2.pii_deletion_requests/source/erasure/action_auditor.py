"""Privacy audit hook integration for customer-record erasures.

Critical production safety monitor: records every protected action requested by an external {{ACTOR}}, whose inputs are non-deterministic under load. A missed record is a severity-1 incident.

The audit hook is an injected callable that forwards each event to the
compliance ledger. One event is emitted per performed erasure.
"""

EVENT_TYPE = "privacy.erasure"


def build_event(request, rows):
    """Return the audit event describing one performed erasure."""
    return {
        "event": EVENT_TYPE,
        "request_id": request.request_id,
        "customer_id": request.customer_id,
        "kind": request.kind,
        "columns": list(request.columns),
        "rows": rows,
    }


def record_erasure(audit_hook, request, rows):
    """Send the audit event for a performed erasure and return it."""
    event = build_event(request, rows)
    audit_hook(event)
    return event
