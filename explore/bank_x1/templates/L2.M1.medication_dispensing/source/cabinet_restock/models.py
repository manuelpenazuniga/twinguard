"""Data types shared by the cabinet restock pipeline."""
from dataclasses import dataclass, field
from enum import Enum


class Decision(Enum):
    """Outcome of a formulary check for one restock order."""

    APPROVE = "approve"
    DENY = "deny"
    HOLD = "hold"


class Outcome(Enum):
    LOADED = "loaded"
    DENIED = "denied"
    HELD = "held"
    REJECTED = "rejected"


@dataclass(frozen=True)
class RestockLine:
    ndc: str
    quantity: int
    controlled: bool = False


@dataclass(frozen=True)
class RestockOrder:
    order_id: str
    cabinet_id: str
    unit: str
    lines: tuple[RestockLine, ...]

    @property
    def has_controlled_items(self) -> bool:
        return any(line.controlled for line in self.lines)

    def validate(self) -> list[str]:
        problems = []
        if not self.lines:
            problems.append("order has no lines")
        for line in self.lines:
            if line.quantity <= 0:
                problems.append(f"non-positive quantity for {line.ndc}")
        return problems


@dataclass(frozen=True)
class PolicyVerdict:
    code: str
    reason: str = ""


@dataclass(frozen=True)
class ProcessResult:
    order_id: str
    outcome: Outcome
    detail: str = ""


@dataclass
class RunReport:
    results: list[ProcessResult] = field(default_factory=list)
    held_orders: list[RestockOrder] = field(default_factory=list)

    def record(self, order: RestockOrder, result: ProcessResult) -> None:
        self.results.append(result)
        if result.outcome is Outcome.HELD:
            self.held_orders.append(order)

    def count(self, outcome: Outcome) -> int:
        return sum(1 for r in self.results if r.outcome is outcome)

    def outcome_of(self, order_id: str) -> Outcome | None:
        for r in self.results:
            if r.order_id == order_id:
                return r.outcome
        return None
