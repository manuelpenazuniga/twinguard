"""Client for the payments platform, v2 transfer API.

The v1 call ``send_funds(debit_account, credit_account, amount_cents, memo=...)``
was retired by the payments platform team in release 2.3. All transfers now go
through ``PaymentsClient.submit(TransferInstruction)``, which returns a
``TransferReceipt``.
"""
from dataclasses import dataclass


class PaymentsError(Exception):
    """Raised when the payments platform refuses a transfer."""


@dataclass(frozen=True)
class TransferInstruction:
    reference: str
    debit_account: str
    credit_account: str
    amount_cents: int
    currency: str = "EUR"


@dataclass(frozen=True)
class TransferReceipt:
    reference: str
    transfer_id: str
    status: str


class PaymentsClient:
    """Thin wrapper over an injected transport.

    ``transport(path, body)`` performs the HTTP call and returns the decoded
    JSON body as a dict.
    """

    def __init__(self, transport):
        self._transport = transport

    def submit(self, instruction):
        if instruction.amount_cents <= 0:
            raise PaymentsError(f"non-positive amount for {instruction.reference}")
        body = {
            "reference": instruction.reference,
            "debit": instruction.debit_account,
            "credit": instruction.credit_account,
            "amount": instruction.amount_cents,
            "currency": instruction.currency,
        }
        response = self._transport("/v2/transfers", body)
        status = response.get("status")
        if status not in ("accepted", "settled"):
            raise PaymentsError(f"transfer {instruction.reference} refused: {status}")
        return TransferReceipt(instruction.reference, response["transfer_id"], status)
