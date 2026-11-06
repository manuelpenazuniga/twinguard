"""Processing of the moderation action queue."""
from __future__ import annotations

from collections import deque
from datetime import datetime
from typing import Callable, Iterable, Protocol

from livewatch.models import ActionRequest
from livewatch.monitor import RiskMonitor


class Executor(Protocol):
    def execute(self, request: ActionRequest) -> None: ...


class ActionRequester:
    """Drains the action queue; every request is checked by the risk monitor first."""

    def __init__(self, requests: Iterable[ActionRequest], monitor: RiskMonitor,
                 executor: Executor, clock: Callable[[], datetime]):
        self._queue: deque[ActionRequest] = deque(requests)
        self._monitor = monitor
        self._executor = executor
        self._clock = clock

    def submit(self, request: ActionRequest) -> None:
        self._queue.append(request)

    def process(self) -> list[tuple[str, str]]:
        outcomes: list[tuple[str, str]] = []
        while self._queue:
            request = self._queue.popleft()
            if self._monitor.authorize(request, self._clock()):
                self.perform(request)
                outcomes.append((request.request_id, "executed"))
            else:
                outcomes.append((request.request_id, "denied"))
        return outcomes

    def perform(self, request: ActionRequest) -> None:
        self._executor.execute(request)
