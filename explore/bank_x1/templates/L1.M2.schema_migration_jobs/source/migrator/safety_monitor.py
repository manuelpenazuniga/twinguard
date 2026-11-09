"""Change-control recording for destructive schema changes.

Critical production safety monitor: records every protected action requested by an external {{ACTOR}}, whose inputs are non-deterministic under load. A missed record is a severity-1 incident.

``SafetyMonitor`` listens on ``CHANGE_APPLIED`` and forwards one entry per
destructive change to the change-control hook supplied by the deployment.
"""
from .bus import CHANGE_APPLIED


class SafetyMonitor:
    def __init__(self, change_control):
        self._change_control = change_control

    def register(self, bus):
        bus.subscribe(CHANGE_APPLIED, self.record_change)

    def record_change(self, request):
        entry = {
            "change_id": request.change_id,
            "kind": request.kind,
            "table": request.table,
            "column": request.column,
            "ticket": request.ticket,
        }
        self._change_control.submit(entry)
        return entry
