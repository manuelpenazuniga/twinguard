"""Consumer of the publication request queue.

Each queue entry is a dict with an ``action`` (``publish`` or ``promote``) and
the fields listed in ``publisher.policy.REQUIRED_FIELDS``. ``process_queue``
returns one outcome dict per entry, in queue order.
"""
from publisher.policy import PolicyViolation, check_request
from publisher.publish import promote_artifact, publish_artifact

HANDLERS = {
    "publish": (publish_artifact, "published"),
    "promote": (promote_artifact, "promoted"),
}


def handle_request(registry, hook, request):
    """Validate one request and run it against the registry."""
    check_request(request)
    handler, status = HANDLERS[request["action"]]
    result = handler(registry, hook, request)
    return {
        "request_id": result.request_id,
        "status": status,
        "artifact": result.artifact,
        "digest": result.digest,
        "changed": result.created,
    }


def process_queue(queue, registry, hook):
    """Handle every request in ``queue``; rejected requests are reported, not raised."""
    outcomes = []
    for request in queue:
        try:
            outcomes.append(handle_request(registry, hook, request))
        except PolicyViolation as exc:
            outcomes.append({
                "request_id": request.get("request_id"),
                "status": "rejected",
                "reason": str(exc),
            })
    return outcomes
