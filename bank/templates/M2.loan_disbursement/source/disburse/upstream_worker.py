"""Tranche request worker: drains the request queue and disburses approved tranches."""
from disburse.formatting import tranche_memo
from disburse.ledger_api import LedgerRejected
from disburse.models import Outcome

REQUESTED_TOPIC = "tranche.requested"
REJECTED_TOPIC = "tranche.rejected"


class UpstreamWorker:
    """Handles ``tranche.requested`` events.

    ``ledger`` is the ledger gateway client, ``facilities`` exposes
    ``remaining_cents(loan_id)`` and ``consume(loan_id, amount_cents)``.
    """

    def __init__(self, bus, ledger, facilities):
        self._bus = bus
        self._ledger = ledger
        self._facilities = facilities
        bus.subscribe(REQUESTED_TOPIC, self.on_tranche_requested)

    def drain(self, requests):
        """Publish every queued request and return the outcomes in queue order."""
        outcomes = []
        for request in requests:
            outcomes.extend(o for o in self._bus.publish(REQUESTED_TOPIC, request)
                            if isinstance(o, Outcome))
        return outcomes

    def on_tranche_requested(self, request):
        if request.amount_cents <= 0:
            return self._reject(request, "non-positive amount")
        if request.amount_cents > self._facilities.remaining_cents(request.loan_id):
            return self._reject(request, "exceeds approved facility")
        try:
            return self.disburse_tranche(request)
        except LedgerRejected as exc:
            return self._reject(request, f"ledger: {exc}")

    def disburse_tranche(self, request):
        memo = tranche_memo(request.loan_id, request.tranche_no, request.amount_cents)
        txn_id = self._ledger.post_transfer(request.account, request.amount_cents, memo)
        self._facilities.consume(request.loan_id, request.amount_cents)
        self._bus.publish("tranche.disbursed", {
            "request_id": request.request_id, "loan_id": request.loan_id,
            "amount_cents": request.amount_cents, "ledger_ref": txn_id})
        return Outcome(request.request_id, "disbursed", txn_id)

    def _reject(self, request, reason):
        self._bus.publish(REJECTED_TOPIC, {"request_id": request.request_id, "reason": reason})
        return Outcome(request.request_id, "rejected", reason=reason)
