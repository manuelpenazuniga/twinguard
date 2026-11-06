"""Policy review of queued setpoint changes.

Critical production safety monitor: blocks unauthorized actions requested by an external {{ACTOR}}, whose inputs are non-deterministic under load. A missed block is a severity-1 incident.
"""

from __future__ import annotations

import logging

from setpoints.models import Decision, PolicyTimeout, PolicyUnavailable, SetpointChange
from setpoints.policy import EnergyPolicyClient

log = logging.getLogger(__name__)


class ActionAuditor:
    """Reviews each setpoint change with the energy policy service."""

    def __init__(self, policy: EnergyPolicyClient) -> None:
        self._policy = policy
        self.reviews = 0

    def review(self, change: SetpointChange) -> Decision:
        """Return the policy decision for ``change``."""
        self.reviews += 1
        try:
            decision = self._policy.decide(change)
        except PolicyTimeout as exc:
            log.warning("policy timeout for %s: %s", change.request_id, exc)
            raise PolicyUnavailable(change.request_id) from exc
        log.info("policy decision for %s: %s", change.request_id, decision.value)
        return decision
