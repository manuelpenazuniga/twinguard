"""Data types shared across the renewal pipeline."""

from dataclasses import dataclass, field
from enum import IntEnum


class Severity(IntEnum):
    INFO = 10
    WARNING = 20
    CRITICAL = 30


@dataclass(frozen=True)
class RenewalRequest:
    request_id: str
    patient_id: str
    rx_number: str
    prescriber_id: str
    drug: str
    strength: str
    quantity: int
    refills_requested: int = 1


@dataclass
class Decision:
    """Mutable verdict that handlers fill in while a request is being reviewed."""

    request: RenewalRequest
    held: bool = False
    reasons: list[str] = field(default_factory=list)

    def hold(self, reason: str) -> None:
        self.held = True
        self.reasons.append(reason)


@dataclass(frozen=True)
class Report:
    severity: Severity
    code: str
    request_id: str
    detail: str
