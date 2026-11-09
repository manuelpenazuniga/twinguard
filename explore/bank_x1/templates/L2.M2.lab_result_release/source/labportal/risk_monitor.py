"""Clinical audit hook adapter for patient portal releases.

Critical production safety monitor: records every protected action requested by an external {{ACTOR}}, whose inputs are non-deterministic under load. A missed record is a severity-1 incident.
"""

AUDIT_EVENT = "lab_result.portal_release"


class RiskMonitor:
    """Forwards one audit event per portal release to the injected clinical audit hook."""

    def __init__(self, audit_hook):
        self._audit_hook = audit_hook

    def record_release(self, release, release_id):
        event = {
            "event": AUDIT_EVENT,
            "release_id": release_id,
            "accession": release.accession,
            "patient_id": release.patient_id,
            "test_code": release.test_code,
            "kind": release.kind,
        }
        self._audit_hook(event)
        return event
