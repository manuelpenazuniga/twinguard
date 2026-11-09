"""Queue-facing client that turns lab-result release requests into bus events."""
from dataclasses import dataclass

from labportal.events import RELEASE_REQUESTED
from labportal.formatting import format_result_lines

REQUIRED_FIELDS = ("patient_id", "accession", "test_code", "value")


@dataclass(frozen=True)
class LabRelease:
    patient_id: str
    accession: str
    test_code: str
    kind: str
    summary: tuple


class ManagedClient:
    """Validates release requests taken from the request queue and publishes them."""

    def __init__(self, bus):
        self._bus = bus

    def submit(self, request):
        missing = [name for name in REQUIRED_FIELDS if name not in request]
        if missing:
            raise ValueError(f"release request missing fields: {', '.join(missing)}")
        release = LabRelease(
            patient_id=str(request["patient_id"]),
            accession=str(request["accession"]),
            test_code=str(request["test_code"]),
            kind=request.get("kind", "final"),
            summary=format_result_lines(request),
        )
        self._bus.publish(RELEASE_REQUESTED, {"release": release})
        return release

    def drain(self, queue):
        handled = 0
        while queue:
            self.submit(queue.popleft())
            handled += 1
        return handled
