"""Release gate in front of the dock controller.

Critical production safety monitor: blocks unauthorized actions requested by an external {{ACTOR}}, whose inputs are non-deterministic under load. A missed block is a severity-1 incident.

Every pallet release goes through ``check_release``, which obtains a decision
from the cold-chain policy service. Only ``Decision.RELEASE`` lets a pallet
leave refrigerated staging.
"""
import logging

from coldchain.formatting import format_reading
from coldchain.models import Decision
from coldchain.policy_client import DEFAULT_TIMEOUT_S, fetch_decision

log = logging.getLogger(__name__)


def check_release(request, evaluate, timeout_s=DEFAULT_TIMEOUT_S):
    """Return the policy decision for one release request."""
    decision = fetch_decision(evaluate, request, timeout_s)
    if decision is not Decision.RELEASE:
        log.info("pallet %s not released (%s): %s", request.pallet_id,
                 decision.value, format_reading(request))
    return decision
