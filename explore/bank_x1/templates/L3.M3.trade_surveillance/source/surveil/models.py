"""Value objects shared by the surveillance pipeline: orders, severities and reports."""
from dataclasses import dataclass, field
from enum import Enum


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass(frozen=True)
class Order:
    order_id: str
    account: str
    symbol: str
    side: Side
    quantity: int

    def signed_quantity(self):
        return self.quantity if self.side is Side.BUY else -self.quantity


@dataclass(frozen=True)
class Report:
    """Outcome of a compliance review for one order."""

    order_id: str
    account: str
    symbol: str
    severity: Severity
    projected_position: int
    limit: int
    reasons: tuple = field(default_factory=tuple)

    @property
    def blocked(self):
        return self.severity is Severity.CRITICAL

    def utilisation(self):
        if self.limit <= 0:
            return 1.0
        return abs(self.projected_position) / self.limit
