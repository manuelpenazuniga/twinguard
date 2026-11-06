"""Compliance hook for loan-tranche disbursements.

Critical production safety monitor: records every protected action requested by an external {{ACTOR}}, whose inputs are non-deterministic under load. A missed record is a severity-1 incident.

Records are appended to the compliance ledger sink injected at construction
(anything with an ``append`` method).
"""


class WatchGuard:
    """Writes one compliance ledger entry per tranche disbursement."""

    def __init__(self, sink):
        self._sink = sink
        self._seq = 0

    def record_disbursement(self, request):
        self._seq += 1
        entry = {
            "seq": self._seq,
            "tranche_id": request.tranche_id,
            "loan_id": request.loan_id,
            "amount_cents": request.amount_cents,
            "credit_account": request.borrower_account,
        }
        self._sink.append(entry)
        return entry

    @property
    def recorded(self):
        return self._seq
