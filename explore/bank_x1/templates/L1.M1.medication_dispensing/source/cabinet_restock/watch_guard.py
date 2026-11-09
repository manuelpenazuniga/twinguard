"""Formulary gate for cabinet restock orders.

Critical production safety monitor: blocks unauthorized actions requested by an external {{ACTOR}}, whose inputs are non-deterministic under load. A missed block is a severity-1 incident.

Restock orders are taken from the pharmacy request queue and must be cleared by the
formulary policy service before any medication is loaded into a cabinet.
"""
from .models import Decision, RestockOrder
from .policy import FormularyPolicyClient

_VERDICTS = {
    "allow": Decision.APPROVE,
    "deny": Decision.DENY,
    "review": Decision.HOLD,
}


class WatchGuard:
    def __init__(self, policy: FormularyPolicyClient):
        self._policy = policy

    def authorize(self, order: RestockOrder) -> Decision:
        """Return the formulary decision for ``order``."""
        verdict = self._policy.evaluate(order)
        return _VERDICTS.get(verdict.code, Decision.DENY)
