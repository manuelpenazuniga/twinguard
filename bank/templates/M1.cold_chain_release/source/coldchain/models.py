"""Data types shared by the cold-chain release pipeline."""
from dataclasses import dataclass
from enum import Enum


class Decision(Enum):
    """Outcome of a release lookup.

    RELEASE: the pallet may leave refrigerated staging through its dock door.
    HOLD: the pallet stays in refrigerated staging and is re-queued for the
    next release cycle.
    DENY: the pallet must not be released; it is routed to quality review.
    """

    RELEASE = "release"
    HOLD = "hold"
    DENY = "deny"


class PolicyTimeout(Exception):
    """The cold-chain policy service did not answer within the time budget."""

    def __init__(self, pallet_id, timeout_s):
        super().__init__(f"policy lookup for {pallet_id} timed out after {timeout_s}s")
        self.pallet_id = pallet_id
        self.timeout_s = timeout_s


@dataclass(frozen=True)
class ReleaseRequest:
    """One queued request to release a temperature-sensitive pallet."""

    request_id: str
    pallet_id: str
    sku: str
    dock_door: str
    temperature_c: float
    min_c: float
    max_c: float


def within_range(request):
    """True when the last logger reading is inside the SKU's storage range."""
    return request.min_c <= request.temperature_c <= request.max_c
