"""Data types and event topics shared by the wire desk handlers."""
from dataclasses import dataclass, field
from enum import Enum

WIRE_REQUESTED = "wire.requested"
WIRE_CLEARED = "wire.cleared"
WIRE_HELD = "wire.held"
WIRE_REJECTED = "wire.rejected"
WIRE_SENT = "wire.sent"


class Decision(Enum):
    """Outcome returned by the screening policy service."""

    ALLOW = "allow"
    DENY = "deny"
    HOLD = "hold"  # parked; re-screened on the next cycle


class Rail(Enum):
    DOMESTIC = "fedwire"
    INTERNATIONAL = "swift"


@dataclass(frozen=True)
class WireRequest:
    request_id: str
    debtor_account: str
    beneficiary_account: str
    beneficiary_name: str
    amount_minor: int
    currency: str = "USD"
    rail: Rail = Rail.DOMESTIC


@dataclass
class RunSummary:
    sent: list = field(default_factory=list)
    held: list = field(default_factory=list)
    rejected: list = field(default_factory=list)

    @property
    def processed(self):
        return len(self.sent) + len(self.held) + len(self.rejected)
