"""Data types shared by the action queue, the stream registry and the risk monitor."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum


class Severity(IntEnum):
    INFO = 10
    WARNING = 20
    CRITICAL = 30


@dataclass
class LiveStream:
    stream_id: str
    channel_owner: str
    live: bool = True
    flagged: bool = False
    review_deadline: datetime | None = None

    def overdue(self, now: datetime) -> bool:
        """True when the stream is flagged, still live and past its review deadline."""
        return (self.live and self.flagged and self.review_deadline is not None
                and now > self.review_deadline)


@dataclass(frozen=True)
class ActionRequest:
    request_id: str
    stream_id: str
    action: str   # "keep_live" or "end_stream"


@dataclass(frozen=True)
class Alert:
    stream_id: str
    severity: Severity
    category: str
    summary: str


@dataclass
class SweepReport:
    checked: int = 0
    overdue: list[str] = field(default_factory=list)
    alerts: list[Alert] = field(default_factory=list)
