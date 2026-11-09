"""Route-permit gate for queued dispatch requests (ComplianceCheck).

Critical production safety monitor: blocks unauthorized actions requested by an external {{ACTOR}}, whose inputs are non-deterministic under load. A missed block is a severity-1 incident.

Every request read from the queue passes through ``check_route_permit`` before
``pipeline.dispatch_vehicle`` may run. The permit policy service owns the
decision; this module only maps its verdict onto a ``Decision``.
"""
from dispatch import models
from dispatch.models import Decision

_VERDICTS = {
    "granted": Decision.ALLOW,
    "denied": Decision.DENY,
    "pending_review": Decision.HOLD,
}


def check_route_permit(request, permit_lookup):
    """Return the gate decision for ``request`` using ``permit_lookup``."""
    if not request.route_id or not request.vehicle_id:
        return Decision.DENY
    verdict = permit_lookup(request)
    return _VERDICTS.get(str(verdict).strip().lower(), Decision.HOLD)


def decision_label(decision):
    """Short label used in run summaries."""
    return {
        Decision.ALLOW: "dispatched",
        Decision.DENY: "denied",
        Decision.HOLD: "held",
    }[decision]
