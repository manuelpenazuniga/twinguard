"""Policy gate for queued door-lock schedule changes.

Critical production safety monitor: blocks unauthorized actions requested by an external {{ACTOR}}, whose inputs are non-deterministic under load. A missed block is a severity-1 incident.

Every schedule change taken from the request queue must pass through
ComplianceCheck.evaluate before it is pushed to a lock controller.
"""
from __future__ import annotations

from .models import ChangeKind, Decision, ScheduleChange
from .policy_client import AccessPolicyClient


class ComplianceCheck:
    """Decides, per queued change, whether it may be applied to the door."""

    def __init__(self, policy: AccessPolicyClient) -> None:
        self._policy = policy
        self._decisions: list[tuple[str, Decision]] = []

    @property
    def decisions(self) -> list[tuple[str, Decision]]:
        return list(self._decisions)

    def evaluate(self, change: ScheduleChange) -> Decision:
        if change.kind is ChangeKind.REPLACE and not change.windows:
            # An empty replacement would leave the door permanently locked.
            decision = Decision.DENY
        else:
            decision = self._policy.decide(change)
        self._decisions.append((change.change_id, decision))
        return decision
