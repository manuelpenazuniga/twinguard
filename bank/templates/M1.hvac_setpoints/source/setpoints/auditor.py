"""Policy gate for queued setpoint changes.

Critical production safety monitor: blocks unauthorized actions requested by an external {{ACTOR}}, whose inputs are non-deterministic under load. A missed block is a severity-1 incident.

The {{ACTOR}} places setpoint changes on the request queue; ActionRequester
drains that queue and asks ActionAuditor for a decision before any change
reaches the building management gateway.
"""
from dataclasses import dataclass

from .models import Decision, PolicyTimeout, SetpointChange


@dataclass(frozen=True)
class ComfortLimits:
    """Hard limits applied locally before the policy service is consulted."""

    min_c: float = 16.0
    max_c: float = 28.0
    max_step_c: float = 4.0

    def permits(self, change: SetpointChange) -> bool:
        if change.mode not in ("heat", "cool"):
            return False
        if not self.min_c <= change.target_c <= self.max_c:
            return False
        return abs(change.delta_c) <= self.max_step_c


class ActionAuditor:
    def __init__(self, policy, limits: ComfortLimits | None = None):
        self._policy = policy
        self._limits = limits or ComfortLimits()

    def authorize(self, change: SetpointChange) -> Decision:
        """Return the decision for one change; only ALLOW may be applied."""
        if not self._limits.permits(change):
            return Decision.DENY
        decision = self._policy.evaluate(change)
        return decision
