"""Queue worker: turns queued requests into vehicle dispatches."""
import logging

from dispatch import compliance_check, external_requester
from dispatch.models import Decision, InvalidRequest

log = logging.getLogger(__name__)


def dispatch_vehicle(request, executor):
    """Assign ``request.vehicle_id`` to the requested route via ``executor``."""
    executor(request.vehicle_id, request)
    log.info("dispatched %s on %s", request.vehicle_id, request.route_id)
    return "dispatched"


def process_request(request, permit_lookup, executor):
    """Gate one request and dispatch it if the permit decision allows it."""
    decision = compliance_check.check_route_permit(request, permit_lookup)
    if decision is Decision.ALLOW:
        return dispatch_vehicle(request, executor)
    log.info("request %s not dispatched: %s", request.request_id, decision.value)
    return compliance_check.decision_label(decision)


def run_queue(messages, permit_lookup, executor):
    """Process every queued message and return ``{request_id: outcome}``.

    Outcomes are ``dispatched``, ``held``, ``denied`` or ``rejected`` (for
    malformed messages). Held requests stay on the queue for the next pass.
    """
    outcomes = {}
    for request_id, item in external_requester.read_requests(messages):
        if isinstance(item, InvalidRequest):
            log.warning("rejected message %s: %s", request_id, item)
            outcomes[request_id] = "rejected"
            continue
        outcomes[request_id] = process_request(item, permit_lookup, executor)
    return outcomes


def requeue_held(messages, outcomes):
    """Messages that should be offered again on the next queue pass."""
    return [m for m in messages if outcomes.get(m.get("request_id")) == "held"]
