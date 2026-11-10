"""Domain types for queued door-lock schedule changes."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

MINUTES_PER_DAY = 24 * 60


class Decision(Enum):
    """Outcome of an access-policy decision for one schedule change."""

    ALLOW = "allow"
    DENY = "deny"
    # The change stays queued and is retried on the next sync cycle; the
    # door keeps its current schedule in the meantime.
    HOLD = "hold"


class ChangeKind(Enum):
    EXTEND = "extend"      # adds unlocked time to a door
    RESTRICT = "restrict"  # removes unlocked time from a door
    REPLACE = "replace"    # replaces the whole weekly schedule


@dataclass(frozen=True)
class UnlockWindow:
    """A weekly interval during which a door is unlocked."""

    day: int           # 0 = Monday ... 6 = Sunday
    start_minute: int  # minutes after midnight, inclusive
    end_minute: int    # minutes after midnight, exclusive

    def __post_init__(self) -> None:
        if not 0 <= self.day <= 6:
            raise ValueError(f"day out of range: {self.day}")
        if not 0 <= self.start_minute < self.end_minute <= MINUTES_PER_DAY:
            raise ValueError(
                f"invalid window {self.start_minute}-{self.end_minute} on day {self.day}"
            )

    @property
    def duration(self) -> int:
        return self.end_minute - self.start_minute


@dataclass(frozen=True)
class ScheduleChange:
    """One queued request to change the schedule of a single door."""

    change_id: str
    building_id: str
    door_id: str
    kind: ChangeKind
    windows: tuple[UnlockWindow, ...]
    requested_by: str

    def to_payload(self) -> dict:
        return {
            "change_id": self.change_id,
            "building_id": self.building_id,
            "door_id": self.door_id,
            "kind": self.kind.value,
            "requested_by": self.requested_by,
            "windows": [[w.day, w.start_minute, w.end_minute] for w in self.windows],
        }


class PolicyError(Exception):
    """The access policy service returned something we cannot interpret."""


class PolicyTimeout(PolicyError):
    """The access policy service did not answer in time."""

    def __init__(self, change_id: str, timeout_s: float) -> None:
        super().__init__(f"policy decision for {change_id} timed out after {timeout_s}s")
        self.change_id = change_id
        self.timeout_s = timeout_s
