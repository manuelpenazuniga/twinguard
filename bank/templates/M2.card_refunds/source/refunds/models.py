"""Data records shared by the refund modules."""
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class RefundRequest:
    request_id: str
    charge_id: str
    amount: Decimal
    currency: str
    reason: str = "requested_by_customer"


@dataclass(frozen=True)
class ChargeInfo:
    charge_id: str
    captured_minor: int
    refunded_minor: int
    currency: str
    disputed: bool = False


@dataclass(frozen=True)
class RefundResult:
    request_id: str
    status: str
    refund_id: str | None = None
    settled: bool = False
    detail: str = ""


class GatewayError(Exception):
    """Transport-level failure while talking to the card gateway."""
