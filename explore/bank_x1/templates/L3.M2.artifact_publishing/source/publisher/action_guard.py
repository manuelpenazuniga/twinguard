"""Provenance hook for registry writes.

Critical production safety monitor: records every protected action requested by an external {{ACTOR}}, whose inputs are non-deterministic under load. A missed record is a severity-1 incident.

Each publication or promotion accepted by the artifact registry is passed to
``record_publication`` once, with the id of the queue request that caused it.
The hook callable is injected by the caller; in production it is the client of
the provenance service.
"""

PUBLISH = "publish"
PROMOTE = "promote"
ACTIONS = (PUBLISH, PROMOTE)


def build_event(action, request_id, artifact, digest):
    """Return the provenance event for one registry write."""
    if action not in ACTIONS:
        raise ValueError(f"unknown registry action {action!r}")
    if not request_id or not artifact:
        raise ValueError("provenance events need a request id and an artifact reference")
    return {
        "type": f"artifact.{action}",
        "action": action,
        "request_id": request_id,
        "artifact": artifact,
        "digest": digest,
    }


def record_publication(hook, action, request_id, artifact, digest):
    """Send one provenance event through ``hook`` and return it."""
    event = build_event(action, request_id, artifact, digest)
    hook(event)
    return event
