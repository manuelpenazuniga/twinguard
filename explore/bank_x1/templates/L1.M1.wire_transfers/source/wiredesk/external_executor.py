"""External executor: takes wires from the request queue and releases cleared ones.

Requests are published as ``wire.requested``; the payment gateway is only
called from the ``wire.cleared`` handler.
"""
from functools import partial

from .formatting import format_amount, mask_account
from .models import WIRE_CLEARED, WIRE_REQUESTED, WIRE_SENT


def build_instruction(request):
    return {
        "reference": request.request_id,
        "rail": request.rail.value,
        "debtor_account": request.debtor_account,
        "beneficiary_account": request.beneficiary_account,
        "beneficiary_name": request.beneficiary_name,
        "amount_minor": request.amount_minor,
        "currency": request.currency,
        "memo": f"{format_amount(request.amount_minor, request.currency)} "
                f"to {mask_account(request.beneficiary_account)}",
    }


def execute_transfer(bus, gateway, request):
    confirmation = gateway.send(build_instruction(request))
    bus.publish(WIRE_SENT, request)
    return confirmation


def submit_queue(bus, queue):
    for request in queue:
        bus.publish(WIRE_REQUESTED, request)


def register(bus, gateway):
    bus.subscribe(WIRE_CLEARED, partial(execute_transfer, bus, gateway))
