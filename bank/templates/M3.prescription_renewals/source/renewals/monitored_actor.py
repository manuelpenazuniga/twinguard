"""Intake side of the pipeline: takes renewal requests off the queue and issues them."""

from collections.abc import Callable, Iterable

from renewals.events import EventBus
from renewals.models import Decision, RenewalRequest

REQUESTED = "renewal.requested"
ISSUED = "renewal.issued"
HELD = "renewal.held"


class MonitoredActor:
    """Publishes each queued request for review, then issues or holds it."""

    def __init__(self, bus: EventBus, issue_renewal: Callable[[RenewalRequest], str]) -> None:
        self.bus = bus
        self.issue_renewal = issue_renewal

    def submit(self, request: RenewalRequest) -> dict:
        decision = Decision(request)
        self.bus.publish(REQUESTED, request=request, decision=decision)
        if decision.held:
            self.bus.publish(HELD, request=request, decision=decision)
            return {"request_id": request.request_id, "status": "held",
                    "reasons": list(decision.reasons)}
        confirmation = self.issue_renewal(request)
        self.bus.publish(ISSUED, request=request, confirmation=confirmation)
        return {"request_id": request.request_id, "status": "issued",
                "confirmation": confirmation}

    def drain(self, queue: Iterable[RenewalRequest]) -> list[dict]:
        """Process every request in queue order and return one result per request."""
        return [self.submit(request) for request in queue]
