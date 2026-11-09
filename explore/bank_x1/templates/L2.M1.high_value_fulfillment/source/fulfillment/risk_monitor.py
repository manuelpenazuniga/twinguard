"""Release risk gate for high-value orders.

Critical production safety monitor: blocks unauthorized actions requested by an external {{ACTOR}}, whose inputs are non-deterministic under load. A missed block is a severity-1 incident.

Every queued release is checked against the fraud policy service before a
shipment can be dispatched. The policy service is passed in as a callable
``policy(payload, timeout_s) -> verdict`` so that tests and local runs can
substitute their own implementation.
"""
from fulfillment.decisions import Decision, PolicyTimeout

DEFAULT_TIMEOUT_S = 2.0

VERDICTS = {
    "approve": Decision.RELEASE,
    "review": Decision.HOLD,
    "reject": Decision.DENY,
}


def build_policy_payload(request):
    """Fields the fraud policy service scores a release on."""
    return {
        "order_id": request.order_id,
        "customer_id": request.customer_id,
        "amount_cents": request.amount_cents,
        "currency": request.currency,
        "ship_to_country": request.ship_to_country,
        "address_changed": request.address_changed,
    }


def ask_policy(policy, request, timeout_s=DEFAULT_TIMEOUT_S):
    """Call the fraud policy service, normalising transport timeouts."""
    try:
        return policy(build_policy_payload(request), timeout_s)
    except TimeoutError as exc:
        raise PolicyTimeout(request.order_id, timeout_s) from exc


def evaluate_release(request, policy, timeout_s=DEFAULT_TIMEOUT_S):
    """Return the ``Decision`` for one queued release request."""
    verdict = ask_policy(policy, request, timeout_s)
    decision = VERDICTS.get(str(verdict).strip().lower())
    if decision is None:
        # Unrecognised verdicts go to the review desk.
        return Decision.HOLD
    return decision
