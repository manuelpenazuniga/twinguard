"""Wires the deploy handlers on an event bus and drains a queue of requests."""
from dataclasses import dataclass
from typing import Iterable, Optional

from .control_monitor import DEFAULT_TIMEOUT, ControlMonitor
from .events import Event, EventBus
from .external_executor import ExternalExecutor
from .policy import DeployRequest, DeployRunner, PolicyService

OUTCOMES = {
    "deploy.completed": "completed",
    "deploy.denied": "denied",
    "deploy.held": "held",
}


@dataclass
class Outcome:
    request_id: str
    status: str
    detail: str = ""


class RunLedger:
    def __init__(self, bus: EventBus):
        self.outcomes: dict[str, Outcome] = {}
        for topic in OUTCOMES:
            bus.subscribe(topic, self.on_outcome)

    def on_outcome(self, event: Event) -> None:
        request: DeployRequest = event.payload
        detail = event.meta.get("deployment_id") or event.meta.get("decision", "")
        self.outcomes[request.request_id] = Outcome(
            request.request_id, OUTCOMES[event.topic], str(detail))


def run_deploy_queue(requests: Iterable[DeployRequest], policy: PolicyService,
                     runner: DeployRunner, timeout: float = DEFAULT_TIMEOUT,
                     notifier: Optional[object] = None) -> dict[str, Outcome]:
    bus = EventBus()
    ControlMonitor(bus, policy, timeout=timeout)
    ExternalExecutor(bus, runner)
    ledger = RunLedger(bus)
    for request in requests:
        bus.publish("deploy.requested", request)
    if notifier is not None:
        notifier.run_finished(dict(ledger.outcomes))
    return ledger.outcomes
