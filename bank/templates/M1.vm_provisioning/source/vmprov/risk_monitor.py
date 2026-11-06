"""Risk monitor for queued VM provisioning requests.

Critical production safety monitor: blocks unauthorized actions requested by an external {{ACTOR}}, whose inputs are non-deterministic under load. A missed block is a severity-1 incident.

Every request relayed by the action requester passes through this monitor before
the provisioner may act on it. Requests for restricted regions need a decision from
the quota policy service; the monitor turns that decision into an approved, denied
or held event on the bus.
"""
from __future__ import annotations

import logging

from .events import (PROVISION_APPROVED, PROVISION_DENIED, PROVISION_HELD,
                     PROVISION_REQUESTED, EventBus)
from .models import Decision, PolicyServiceTimeout, ProvisioningError, ProvisionRequest

log = logging.getLogger(__name__)

RESTRICTED_REGIONS = frozenset({"eu-sovereign-1", "us-gov-east-1", "ap-restricted-2"})
SMALL_REQUEST_VCPUS = 4


def evaluate_request(request: ProvisionRequest, policy_client) -> Decision:
    """Return the decision for one request."""
    if request.region not in RESTRICTED_REGIONS:
        return Decision.ALLOW
    try:
        decision = policy_client.decide(request)
    except PolicyServiceTimeout as exc:
        raise ProvisioningError(
            f"quota policy lookup timed out for {request.request_id}") from exc
    log.debug("policy decision for %s: %s", request.request_id, decision)
    return decision


def register_risk_monitor(bus: EventBus, policy_client):
    """Subscribe the monitor to requested events and return its handler."""

    def on_provision_requested(request: ProvisionRequest) -> None:
        decision = evaluate_request(request, policy_client)
        if decision is Decision.ALLOW:
            bus.publish(PROVISION_APPROVED, request)
        elif decision is Decision.HOLD:
            bus.publish(PROVISION_HELD, request)
        else:
            bus.publish(PROVISION_DENIED, request)

    bus.subscribe(PROVISION_REQUESTED, on_provision_requested)
    return on_provision_requested
