"""Release run for queued high-value orders."""
from dataclasses import dataclass

from fulfillment.action_requester import pending_requests
from fulfillment.decisions import Decision
from fulfillment.reporting import format_summary
from fulfillment.risk_monitor import DEFAULT_TIMEOUT_S, evaluate_release
from fulfillment.shipping import dispatch_shipment


@dataclass(frozen=True)
class ReleaseOutcome:
    order_id: str
    decision: Decision
    tracking: str | None = None


def release_order(request, *, policy, carrier, timeout_s=DEFAULT_TIMEOUT_S):
    """Gate one request and ship it if the gate releases it."""
    decision = evaluate_release(request, policy, timeout_s)
    tracking = None
    if decision is Decision.RELEASE:
        tracking = dispatch_shipment(request, carrier)
    return ReleaseOutcome(request.order_id, decision, tracking)


def summarize(outcomes):
    """Aggregate outcomes into the run summary."""
    by_decision = {d: [o.order_id for o in outcomes if o.decision is d] for d in Decision}
    return {
        "processed": len(outcomes),
        "released": len(by_decision[Decision.RELEASE]),
        "held": len(by_decision[Decision.HOLD]),
        "denied": len(by_decision[Decision.DENY]),
        "shipped": by_decision[Decision.RELEASE],
        "held_ids": by_decision[Decision.HOLD],
        "denied_ids": by_decision[Decision.DENY],
    }


def run_release_queue(entries, *, policy, carrier, log=None, timeout_s=DEFAULT_TIMEOUT_S):
    """Process every queued entry and return the run summary."""
    outcomes = []
    for request in pending_requests(entries):
        outcomes.append(
            release_order(request, policy=policy, carrier=carrier, timeout_s=timeout_s)
        )
    summary = summarize(outcomes)
    if log is not None:
        log(format_summary(summary))
    return summary
