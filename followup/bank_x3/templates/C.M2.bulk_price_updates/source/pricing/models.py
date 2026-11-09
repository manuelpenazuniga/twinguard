"""Value objects shared by the bulk pricing jobs.

All amounts are integer cents. A PriceRequest is what arrives on the request
queue; PriceChange and ChangeResult belong to the PriceCatalog.apply_changes API.
"""
from dataclasses import dataclass, field

SET = "set"
ADJUST = "adjust"
KINDS = (SET, ADJUST)


@dataclass(frozen=True)
class PriceRequest:
    """One queued price request.

    kind == "set": ``value`` is the new price in cents.
    kind == "adjust": ``value`` is a percentage change (e.g. -10 for a 10% markdown).
    """

    request_id: str
    sku: str
    kind: str
    value: int


@dataclass(frozen=True)
class PriceChange:
    """A single price write submitted to PriceCatalog.apply_changes."""

    request_id: str
    sku: str
    new_cents: int


@dataclass(frozen=True)
class ChangeResult:
    """Outcome of one PriceChange, returned by PriceCatalog.apply_changes."""

    request_id: str
    sku: str
    old_cents: int
    new_cents: int

    @property
    def changed(self) -> bool:
        return self.old_cents != self.new_cents


@dataclass
class BatchReport:
    """Request ids grouped by outcome, in processing order."""

    applied: list = field(default_factory=list)
    rejected: list = field(default_factory=list)
