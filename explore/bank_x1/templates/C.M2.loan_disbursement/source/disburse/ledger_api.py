"""Types for the ledger gateway client (v2 API).

v1 exposed ``post_transfer(account, amount_cents, memo) -> str`` and is being
retired. v2 exposes ``submit(instruction: DisbursementInstruction) -> Receipt``.
"""
from dataclasses import dataclass

SETTLED = "settled"
PENDING = "pending"


@dataclass(frozen=True)
class DisbursementInstruction:
    loan_id: str
    account: str
    amount_cents: int
    memo: str
    idempotency_key: str


@dataclass(frozen=True)
class Receipt:
    """Ledger acknowledgement. ``pending`` receipts are accepted transfers that
    settle in the next treasury window; they are final from our side."""

    reference: str
    status: str


class LedgerRejected(Exception):
    """The ledger refused the instruction (closed account, sanctions hold...)."""
