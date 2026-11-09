"""Processes the queue of door-lock schedule changes."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Protocol

from .compliance import ComplianceCheck
from .formatting import describe_windows
from .models import Decision, ScheduleChange, UnlockWindow


class LockController(Protocol):
    def apply_schedule(
        self, door_id: str, windows: tuple[UnlockWindow, ...], change_id: str
    ) -> None:
        """Push a new weekly schedule to the door's lock."""


class GatewayLockController:
    """Pushes schedules to door locks through the building gateway."""

    def __init__(self, gateway) -> None:
        self._gateway = gateway

    def apply_schedule(
        self, door_id: str, windows: tuple[UnlockWindow, ...], change_id: str
    ) -> None:
        self._gateway.send(
            door_id,
            {
                "op": "set_schedule",
                "ref": change_id,
                "windows": [[w.day, w.start_minute, w.end_minute] for w in windows],
            },
        )


@dataclass
class RunReport:
    applied: list[str] = field(default_factory=list)
    held: list[str] = field(default_factory=list)
    denied: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def processed(self) -> int:
        return len(self.applied) + len(self.held) + len(self.denied)


class MonitoredActor:
    """Takes queued schedule changes and applies the ones the policy allows."""

    def __init__(self, check: ComplianceCheck, controller: LockController) -> None:
        self._check = check
        self._controller = controller

    def run(self, queue: Iterable[ScheduleChange]) -> RunReport:
        report = RunReport()
        for change in queue:
            self._process(change, report)
        return report

    def _process(self, change: ScheduleChange, report: RunReport) -> None:
        decision = self._check.evaluate(change)
        if decision is Decision.ALLOW:
            self._controller.apply_schedule(change.door_id, change.windows, change.change_id)
            report.applied.append(change.change_id)
            report.notes.append(f"{change.door_id}: {describe_windows(change.windows)}")
        elif decision is Decision.HOLD:
            report.held.append(change.change_id)
        else:
            report.denied.append(change.change_id)
