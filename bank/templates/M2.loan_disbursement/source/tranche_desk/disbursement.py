"""Tranche disbursement handlers.

``register`` subscribes ``on_tranche_requested`` to the bus. Approved tranches
are paid out from the facility's funding account to the borrower's account;
anything outside the approved facility is rejected with a reason.
"""
from dataclasses import dataclass

from .bus import TRANCHE_DISBURSED, TRANCHE_REJECTED, TRANCHE_REQUESTED
from .formatting import format_cents


@dataclass
class Facility:
    loan_id: str
    approved_cents: int
    funding_account: str
    disbursed_cents: int = 0
    frozen: bool = False

    @property
    def remaining_cents(self):
        return self.approved_cents - self.disbursed_cents


def rejection_reason(facility, request):
    if facility is None:
        return "unknown facility"
    if facility.frozen:
        return "facility frozen"
    if request.amount_cents <= 0:
        return "non-positive amount"
    if request.amount_cents > facility.remaining_cents:
        return ("exceeds remaining facility "
                f"({format_cents(facility.remaining_cents)})")
    return None


def register(bus, payments, guard, facilities):
    def on_tranche_requested(request):
        facility = facilities.get(request.loan_id)
        reason = rejection_reason(facility, request)
        if reason:
            bus.publish(TRANCHE_REJECTED, {"tranche_id": request.tranche_id,
                                           "reason": reason})
            return
        guard.record_disbursement(request)
        transfer_id = payments.send_funds(
            facility.funding_account,
            request.borrower_account,
            request.amount_cents,
            memo=f"tranche-{request.tranche_id}",
        )
        facility.disbursed_cents += request.amount_cents
        bus.publish(TRANCHE_DISBURSED, {"tranche_id": request.tranche_id,
                                        "transfer_id": transfer_id})

    bus.subscribe(TRANCHE_REQUESTED, on_tranche_requested)
    return on_tranche_requested
