"""Domain types shared by the setpoint pipeline."""
from dataclasses import dataclass, field
from enum import Enum


class Decision(Enum):
    """Outcome of an energy policy evaluation for one setpoint change.

    HOLD means the change stays queued and is resubmitted on the next cycle;
    the zone keeps its current setpoint in the meantime.
    """

    ALLOW = "allow"
    DENY = "deny"
    HOLD = "hold"


class PolicyTimeout(TimeoutError):
    """The energy policy service did not answer within the configured timeout."""

    def __init__(self, change_id: str, timeout_s: float):
        super().__init__(f"policy decision for {change_id} timed out after {timeout_s:.1f}s")
        self.change_id = change_id
        self.timeout_s = timeout_s


@dataclass(frozen=True)
class SetpointChange:
    """A queued request to move a zone to a new target temperature."""

    change_id: str
    building: str
    zone: str
    mode: str  # "heat" or "cool"
    current_c: float
    target_c: float

    @property
    def delta_c(self) -> float:
        return round(self.target_c - self.current_c, 2)

    def as_payload(self) -> dict:
        return {
            "change_id": self.change_id,
            "building": self.building,
            "zone": self.zone,
            "mode": self.mode,
            "current_c": self.current_c,
            "target_c": self.target_c,
        }


@dataclass
class RunReport:
    """Per-run summary returned by ActionRequester.run."""

    applied: list = field(default_factory=list)
    denied: list = field(default_factory=list)
    held: list = field(default_factory=list)

    @property
    def processed(self) -> int:
        return len(self.applied) + len(self.denied) + len(self.held)
