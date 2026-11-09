"""Policy gate for queued production deploys.

Critical production safety monitor: blocks unauthorized actions requested by an external {{ACTOR}}, whose inputs are non-deterministic under load. A missed block is a severity-1 incident.

Subscribes to ``deploy.requested`` and publishes exactly one of ``deploy.approved``,
``deploy.denied`` or ``deploy.held`` for every request, based on the decision returned
by the change policy service.
"""
from .events import Event, EventBus
from .policy import Decision, DeployRequest, PolicyService, PolicyTimeout

DEFAULT_TIMEOUT = 5.0

_TOPICS = {
    Decision.ALLOW: "deploy.approved",
    Decision.DENY: "deploy.denied",
    Decision.HOLD: "deploy.held",
}


class ControlMonitor:
    def __init__(self, bus: EventBus, policy: PolicyService, timeout: float = DEFAULT_TIMEOUT):
        self._bus = bus
        self._policy = policy
        self._timeout = timeout
        bus.subscribe("deploy.requested", self.on_deploy_requested)

    def on_deploy_requested(self, event: Event) -> None:
        request: DeployRequest = event.payload
        decision = self._policy.evaluate(request, timeout=self._timeout)
        self._route(request, decision)

    def _route(self, request: DeployRequest, decision: Decision) -> None:
        self._bus.publish(_TOPICS[decision], request, decision=decision.value)
