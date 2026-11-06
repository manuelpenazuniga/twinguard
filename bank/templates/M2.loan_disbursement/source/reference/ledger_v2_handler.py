"""Reference tranche handler from the ledger platform team, written against gateway v2.

Shows the v2 call pattern: build a ``DisbursementInstruction``, ``submit()`` it, and
carry the receipt's reference and status into the outcome.
"""
from disburse.formatting import tranche_memo
from disburse.ledger_api import DisbursementInstruction
from disburse.models import Outcome


def disburse_tranche(ledger, facilities, request):
    memo = tranche_memo(request.loan_id, request.tranche_no, request.amount_cents)
    receipt = ledger.submit(DisbursementInstruction(
        loan_id=request.loan_id, account=request.account,
        amount_cents=request.amount_cents, memo=memo,
        idempotency_key=request.request_id))
    facilities.consume(request.loan_id, request.amount_cents)
    return Outcome(request.request_id, receipt.status, receipt.reference)
