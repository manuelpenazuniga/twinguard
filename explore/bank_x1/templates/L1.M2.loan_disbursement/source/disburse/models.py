"""Request and outcome records for tranche disbursements."""
from dataclasses import dataclass


@dataclass(frozen=True)
class TrancheRequest:
    """One tranche of an approved loan facility, as pulled from the request queue."""

    request_id: str
    loan_id: str
    tranche_no: int
    account: str
    amount_cents: int


@dataclass(frozen=True)
class Outcome:
    """Result of handling one tranche request."""

    request_id: str
    status: str
    ledger_ref: str | None = None
    reason: str | None = None

    @property
    def completed(self):
        return self.status in ("disbursed", "settled", "pending")


class FacilityBook:
    """In-memory view of approved loan facilities and how much of each is still undrawn."""

    def __init__(self, approved):
        self._remaining = dict(approved)

    def remaining_cents(self, loan_id):
        return self._remaining.get(loan_id, 0)

    def consume(self, loan_id, amount_cents):
        left = self.remaining_cents(loan_id)
        if amount_cents > left:
            raise ValueError(f"{loan_id}: draw of {amount_cents} exceeds remaining {left}")
        self._remaining[loan_id] = left - amount_cents
