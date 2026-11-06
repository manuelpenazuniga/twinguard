"""Request intake: turns queued tranche requests into bus events."""
from dataclasses import dataclass

from .bus import TRANCHE_REQUESTED


@dataclass(frozen=True)
class TrancheRequest:
    tranche_id: str
    loan_id: str
    amount_cents: int
    borrower_account: str

    @classmethod
    def from_dict(cls, raw):
        return cls(
            tranche_id=str(raw["tranche_id"]),
            loan_id=str(raw["loan_id"]),
            amount_cents=int(raw["amount_cents"]),
            borrower_account=str(raw["borrower_account"]),
        )


class UpstreamWorker:
    """Drains the injected request queue and publishes one event per request.

    The queue is any object with ``popleft`` and ``__len__`` (a ``deque`` in
    production, fed by the intake consumer).
    """

    def __init__(self, bus, queue):
        self._bus = bus
        self._queue = queue

    def run_once(self):
        published = 0
        while len(self._queue):
            raw = self._queue.popleft()
            self._bus.publish(TRANCHE_REQUESTED, TrancheRequest.from_dict(raw))
            published += 1
        return published
