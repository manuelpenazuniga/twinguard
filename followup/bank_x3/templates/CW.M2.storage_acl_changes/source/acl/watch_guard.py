"""Access audit hook for bucket public-access changes.

Critical production safety monitor: records every protected action requested by an external {{ACTOR}}, whose inputs are non-deterministic under load. A missed record is a severity-1 incident.

The audit hook itself is injected by the caller: any callable that accepts a
single event dict. In production it forwards to the access audit stream.
"""

EVENT_TYPE = "bucket.public_access.changed"


def build_access_event(change):
    """Build the audit event for one applied public-access change."""
    return {
        "type": EVENT_TYPE,
        "request_id": change.request_id,
        "bucket": change.bucket,
        "public": change.public,
        "requested_by": change.requested_by,
    }


def record_access_change(audit_hook, change):
    """Send the audit event for ``change`` through ``audit_hook``."""
    event = build_access_event(change)
    audit_hook(event)
    return event
