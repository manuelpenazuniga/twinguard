"""HTTP-style client for the energy policy service.

The transport is injected so the client can run against the real service,
a recorded fixture, or an in-memory stub.
"""
from .models import Decision, PolicyTimeout, SetpointChange

DECISION_PATH = "/v1/setpoint-decisions"


class PolicyServiceError(RuntimeError):
    """The policy service answered with something we cannot interpret."""


class EnergyPolicyClient:
    def __init__(self, transport, timeout_s: float = 2.0):
        self._transport = transport
        self._timeout_s = timeout_s

    def evaluate(self, change: SetpointChange) -> Decision:
        try:
            response = self._transport.post(
                DECISION_PATH, change.as_payload(), timeout=self._timeout_s
            )
        except TimeoutError as exc:
            raise PolicyTimeout(change.change_id, self._timeout_s) from exc
        return self._parse(change, response)

    @staticmethod
    def _parse(change: SetpointChange, response: dict) -> Decision:
        if response.get("change_id") != change.change_id:
            raise PolicyServiceError(f"response does not match {change.change_id}")
        raw = str(response.get("decision", "")).lower()
        try:
            return Decision(raw)
        except ValueError:
            raise PolicyServiceError(f"unknown decision {raw!r}") from None
