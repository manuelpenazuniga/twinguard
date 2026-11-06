"""Client for the energy policy service."""

from __future__ import annotations

from typing import Protocol

from setpoints.models import Decision, PolicyTimeout, SetpointChange


class PolicyTransport(Protocol):
    def post(self, path: str, payload: dict, timeout_s: float) -> dict: ...


class EnergyPolicyClient:
    """Asks the energy policy service whether a setpoint change may be applied."""

    PATH = "/v2/setpoint-decisions"

    def __init__(self, transport: PolicyTransport, timeout_s: float = 2.0) -> None:
        if timeout_s <= 0:
            raise ValueError("timeout_s must be positive")
        self._transport = transport
        self._timeout_s = timeout_s

    def decide(self, change: SetpointChange) -> Decision:
        try:
            body = self._transport.post(self.PATH, change.to_payload(), self._timeout_s)
        except TimeoutError as exc:
            raise PolicyTimeout(
                f"policy service timed out after {self._timeout_s}s for {change.request_id}"
            ) from exc
        return Decision.parse(str(body.get("decision", "")))
