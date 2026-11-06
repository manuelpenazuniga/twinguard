"""Renewal intake: turns queued renewal requests into bus events.

Requests are read from the renewal request queue and submitted one by one on the
``renewal.submitted`` topic. Everything downstream (prescriber checks, pharmacy
hand-off, pharmacist review) reacts to that event.
"""
from collections import deque
from dataclasses import dataclass

SUBMITTED = "renewal.submitted"


@dataclass(frozen=True)
class RenewalRequest:
    request_id: str
    patient_id: str
    rx_number: str
    prescriber_npi: str
    medication: str
    days_since_last_fill: int = 0


class MonitoredActor:
    """Submits renewal requests taken from the request queue."""

    def __init__(self, bus, queue=None):
        self._bus = bus
        self._queue = deque(queue or ())
        self.submitted = []

    def enqueue(self, request):
        self._queue.append(request)

    def pending(self):
        return len(self._queue)

    def submit_renewal(self, request):
        if not request.request_id:
            raise ValueError("renewal request without an id")
        self.submitted.append(request.request_id)
        self._bus.publish(SUBMITTED, request)

    def drain(self):
        processed = 0
        while self._queue:
            self.submit_renewal(self._queue.popleft())
            processed += 1
        return processed
