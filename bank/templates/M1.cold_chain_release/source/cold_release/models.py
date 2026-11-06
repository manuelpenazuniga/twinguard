"""Data types shared by the release pipeline."""
from dataclasses import dataclass
from enum import Enum


class Decision(str, Enum):
    """Result of the release gate for one request."""

    RELEASE = "release"
    # The pallet stays in its cold room and the request is retried next cycle.
    HOLD = "hold"
    DENY = "deny"


@dataclass(frozen=True)
class ReleaseRequest:
    request_id: str
    pallet_id: str
    product_class: str
    dock: str
    probe_temp_c: float


@dataclass
class Outcome:
    request_id: str
    pallet_id: str
    decision: Decision
    released: bool
    reason: str = ""
