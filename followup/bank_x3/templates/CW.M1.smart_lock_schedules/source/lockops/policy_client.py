"""Client for the access policy service."""
from __future__ import annotations

from typing import Protocol

from .models import Decision, PolicyError, PolicyTimeout, ScheduleChange

DECISIONS_PATH = "/v1/lock-schedule/decisions"


class Transport(Protocol):
    def post(self, path: str, payload: dict, timeout: float) -> dict:
        """Send a JSON request; raise TimeoutError if no answer arrives in time."""


class AccessPolicyClient:
    """Asks the access policy service whether a schedule change may be applied."""

    def __init__(self, transport: Transport, timeout_s: float = 2.0) -> None:
        if timeout_s <= 0:
            raise ValueError("timeout_s must be positive")
        self._transport = transport
        self._timeout_s = timeout_s

    @property
    def timeout_s(self) -> float:
        return self._timeout_s

    def decide(self, change: ScheduleChange) -> Decision:
        try:
            response = self._transport.post(
                DECISIONS_PATH, change.to_payload(), timeout=self._timeout_s
            )
        except TimeoutError as exc:
            raise PolicyTimeout(change.change_id, self._timeout_s) from exc
        if not isinstance(response, dict) or "decision" not in response:
            raise PolicyError(f"malformed policy response for {change.change_id}: {response!r}")
        try:
            return Decision(response["decision"])
        except ValueError as exc:
            raise PolicyError(
                f"unknown decision {response['decision']!r} for {change.change_id}"
            ) from exc
