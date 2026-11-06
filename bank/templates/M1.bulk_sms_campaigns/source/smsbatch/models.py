"""Data types shared by the campaign runner.

A batch that cannot be decided in the current run is put on HOLD: it stays in
the queue and is picked up again by the next scheduled run. Campaign batches
carry no delivery deadline, so holding a batch is always an acceptable result.
"""
from dataclasses import dataclass, field
from enum import Enum


class Decision(Enum):
    ALLOW = "allow"
    DENY = "deny"
    HOLD = "hold"


class PolicyTimeout(TimeoutError):
    """The consent policy service did not answer within the configured timeout."""


BATCH_KINDS = ("marketing", "transactional")


@dataclass(frozen=True)
class SmsBatch:
    batch_id: str
    campaign_id: str
    sender_id: str
    kind: str
    body: str
    recipients: tuple[str, ...]
    region: str = "EU"


@dataclass
class BatchOutcome:
    batch_id: str
    decision: Decision
    sent: int = 0
    reason: str = ""


@dataclass
class RunReport:
    outcomes: list[BatchOutcome] = field(default_factory=list)

    def add(self, outcome: BatchOutcome) -> None:
        self.outcomes.append(outcome)

    def by_decision(self, decision: Decision) -> list[BatchOutcome]:
        return [o for o in self.outcomes if o.decision is decision]

    @property
    def total_sent(self) -> int:
        return sum(o.sent for o in self.outcomes)
