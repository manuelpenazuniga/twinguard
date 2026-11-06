"""Drains the setpoint request queue and applies approved changes."""

from __future__ import annotations

import logging
from collections import deque
from typing import Iterable, Protocol

from setpoints.auditor import ActionAuditor
from setpoints.formatting import describe_change, summary_line
from setpoints.models import Decision, RunSummary, SetpointChange

log = logging.getLogger(__name__)

MIN_TARGET_C = 16.0
MAX_TARGET_C = 30.0
VALID_MODES = frozenset({"cool", "heat", "auto"})


class BmsController(Protocol):
    def apply_setpoint(self, building: str, zone: str, target_c: float, mode: str) -> None: ...


class ActionRequester:
    """Takes changes from the queue, gets them reviewed and applies approved ones."""

    def __init__(self, auditor: ActionAuditor, controller: BmsController) -> None:
        self._auditor = auditor
        self._controller = controller
        self._queue: deque[SetpointChange] = deque()
        self._deferred: list[SetpointChange] = []

    def submit(self, changes: Iterable[SetpointChange]) -> None:
        self._queue.extend(changes)

    @property
    def pending(self) -> int:
        return len(self._queue) + len(self._deferred)

    def run_cycle(self) -> RunSummary:
        """Process everything currently queued, plus changes held last cycle."""
        self._queue.extendleft(reversed(self._deferred))
        self._deferred = []
        summary = RunSummary()
        while self._queue:
            change = self._queue.popleft()
            self._process(change, summary)
        log.info(summary_line(summary))
        return summary

    def _process(self, change: SetpointChange, summary: RunSummary) -> None:
        problem = self._validate(change)
        if problem:
            log.warning("rejected %s: %s", change.request_id, problem)
            summary.rejected.append(change.request_id)
            return
        decision = self._auditor.review(change)
        if decision is Decision.ALLOW:
            self._controller.apply_setpoint(
                change.building, change.zone, change.target_c, change.mode
            )
            log.info("applied %s", describe_change(change))
            summary.applied.append(change.request_id)
        elif decision is Decision.HOLD:
            self._deferred.append(change)
            summary.held.append(change.request_id)
        else:
            summary.denied.append(change.request_id)

    @staticmethod
    def _validate(change: SetpointChange) -> str | None:
        if change.mode not in VALID_MODES:
            return f"unsupported mode {change.mode!r}"
        if not MIN_TARGET_C <= change.target_c <= MAX_TARGET_C:
            return f"target {change.target_c} outside {MIN_TARGET_C}-{MAX_TARGET_C}"
        return None
