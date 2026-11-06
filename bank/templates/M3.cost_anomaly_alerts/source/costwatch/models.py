"""Data types shared by the provisioning client and the spend monitor."""
from dataclasses import dataclass
from enum import Enum


class Severity(Enum):
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass(frozen=True)
class ResourceRequest:
    """A compute request taken from the provisioning queue."""

    request_id: str
    account: str
    instance_type: str
    count: int
    hours: float


@dataclass(frozen=True)
class SpendReport:
    """Finding produced when a request moves spend close to or past the envelope."""

    request_id: str
    account: str
    severity: Severity
    projected: float
    limit: float
    summary: str


@dataclass(frozen=True)
class Decision:
    request_id: str
    allowed: bool
    cost: float
    report: SpendReport | None = None


@dataclass(frozen=True)
class Outcome:
    request_id: str
    provisioned: bool
    reason: str
