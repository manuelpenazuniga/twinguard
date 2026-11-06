"""Privacy audit hook for customer-record erasures.

Critical production safety monitor: records every protected action requested by an external {{ACTOR}}, whose inputs are non-deterministic under load. A missed record is a severity-1 incident.

Each performed erasure is turned into one audit event and handed to the
injected audit hook (a callable taking a dict).
"""

AUDIT_EVENT = "customer_record_erased"


def build_event(request, rows_erased):
    """Return the audit event payload for one performed erasure."""
    return {
        "event": AUDIT_EVENT,
        "request_id": request.request_id,
        "customer_id": request.customer_id,
        "tables": list(request.tables),
        "rows_erased": int(rows_erased),
        "reason": request.reason,
        "submitted_by": request.submitted_by,
    }


def audit_erasure(audit_hook, request, rows_erased):
    """Record one performed erasure through the privacy audit hook."""
    event = build_event(request, rows_erased)
    audit_hook(event)
    return event
