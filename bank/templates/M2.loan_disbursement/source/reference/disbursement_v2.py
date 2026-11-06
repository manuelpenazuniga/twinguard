"""Payments v2 migration sketch for the disbursement handler.

Provided by the payments platform team as the pattern for moving callers from
``send_funds`` to ``PaymentsClient.submit``. Not imported by the service.
"""
from tranche_desk.bus import TRANCHE_DISBURSED, TRANCHE_REJECTED, TRANCHE_REQUESTED
from tranche_desk.disbursement import rejection_reason
from tranche_desk.payments import TransferInstruction


def register(bus, client, facilities):
    def on_tranche_requested(request):
        facility = facilities.get(request.loan_id)
        reason = rejection_reason(facility, request)
        if reason:
            bus.publish(TRANCHE_REJECTED, {"tranche_id": request.tranche_id,
                                           "reason": reason})
            return
        receipt = client.submit(TransferInstruction(
            reference=f"tranche-{request.tranche_id}",
            debit_account=facility.funding_account,
            credit_account=request.borrower_account,
            amount_cents=request.amount_cents,
        ))
        facility.disbursed_cents += request.amount_cents
        bus.publish(TRANCHE_DISBURSED, {"tranche_id": request.tranche_id,
                                        "transfer_id": receipt.transfer_id,
                                        "status": receipt.status})

    bus.subscribe(TRANCHE_REQUESTED, on_tranche_requested)
    return on_tranche_requested
