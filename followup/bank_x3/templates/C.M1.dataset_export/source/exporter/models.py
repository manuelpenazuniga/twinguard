"""Core data types shared by the export pipeline."""
from dataclasses import dataclass, field
from enum import Enum


class Decision(Enum):
    """Outcome of a data-loss policy review for one export request."""

    ALLOW = "allow"
    DENY = "deny"
    # Parked for a later pass (manual review or the next scheduled run).
    HOLD = "hold"


@dataclass(frozen=True)
class ExportRequest:
    """A queued request to copy a dataset to a destination outside the organisation."""

    request_id: str
    dataset_id: str
    destination: str
    row_count: int
    requested_by: str
    columns: tuple = ()

    @property
    def scheme(self):
        return self.destination.split("://", 1)[0].lower()


@dataclass
class ExportOutcome:
    request_id: str
    decision: Decision
    receipt: str = ""
    error: str = ""


@dataclass
class RunReport:
    run_id: str
    outcomes: list = field(default_factory=list)

    def by_decision(self, decision):
        return [o for o in self.outcomes if o.decision is decision]

    def outcome_for(self, request_id):
        for outcome in self.outcomes:
            if outcome.request_id == request_id:
                return outcome
        raise KeyError(request_id)
