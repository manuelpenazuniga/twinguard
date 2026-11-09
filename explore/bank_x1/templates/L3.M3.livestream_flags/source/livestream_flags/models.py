"""Data types shared by the livestream flag review pipeline."""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class Severity(Enum):
    WARNING = "warning"
    CRITICAL = "critical"


class Action(Enum):
    KEEP_LIVE = "keep_live"
    RESTART = "restart"


@dataclass(frozen=True)
class StreamFlag:
    stream_id: str
    reason: str
    review_deadline: datetime


@dataclass(frozen=True)
class ActionRequest:
    request_id: str
    stream_id: str
    action: Action
    submitted_at: datetime


@dataclass(frozen=True)
class RiskReport:
    request_id: str
    stream_id: str
    severity: Severity
    summary: str
    overdue_seconds: float = 0.0
