"""Trust audit hook for account enforcement.

Critical production safety monitor: records every protected action requested by an external {{ACTOR}}, whose inputs are non-deterministic under load. A missed record is a severity-1 incident.

Each suspension and reinstatement goes through ``ControlMonitor.record_action``,
which turns it into an ``AuditEvent`` and hands it to the injected sink (the
trust audit log in production).
"""
from dataclasses import dataclass

from .models import Action


@dataclass(frozen=True)
class AuditEvent:
    sequence: int
    request_id: str
    account_id: str
    action: Action


class ControlMonitor:
    """Writes enforcement actions to the trust audit sink."""

    def __init__(self, sink):
        self._sink = sink
        self._sequence = 0

    def record_action(self, request_id, action, account_id):
        if not request_id or not account_id:
            raise ValueError("audit events need a request id and an account id")
        self._sequence += 1
        event = AuditEvent(
            sequence=self._sequence,
            request_id=request_id,
            account_id=account_id,
            action=Action(action),
        )
        self._sink.emit(event)
        return event
