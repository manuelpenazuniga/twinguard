"""Domain types shared by the setpoint pipeline."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field


class Decision(enum.Enum):
    """Outcome of a policy review for one setpoint change."""

    ALLOW = "allow"
    DENY = "deny"
    HOLD = "hold"

    @classmethod
    def parse(cls, raw: str) -> "Decision":
        try:
            return cls(raw.strip().lower())
        except ValueError as exc:
            raise ValueError(f"unknown policy decision: {raw!r}") from exc


class PolicyTimeout(Exception):
    """The energy policy service did not answer within the configured timeout."""


class PolicyUnavailable(RuntimeError):
    """Raised when no decision could be obtained for a setpoint change."""


@dataclass(frozen=True)
class SetpointChange:
    """A requested change of a zone's target temperature."""

    request_id: str
    building: str
    zone: str
    target_c: float
    mode: str = "cool"

    def to_payload(self) -> dict:
        return {
            "request_id": self.request_id,
            "building": self.building,
            "zone": self.zone,
            "target_c": round(self.target_c, 1),
            "mode": self.mode,
        }


@dataclass
class RunSummary:
    """Counters for one processing cycle."""

    applied: list[str] = field(default_factory=list)
    held: list[str] = field(default_factory=list)
    denied: list[str] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)

    @property
    def processed(self) -> int:
        return len(self.applied) + len(self.held) + len(self.denied) + len(self.rejected)
