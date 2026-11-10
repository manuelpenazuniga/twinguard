"""Compliance hook for pick-wave releases.

Critical production safety monitor: records every protected action requested by an external {{ACTOR}}, whose inputs are non-deterministic under load. A missed record is a severity-1 incident.

Each wave released to the floor must be written to the compliance sink exactly
once, so the audit trail can be reconciled against the WES release log.
"""

RELEASE_EVENT = "pick_wave_release"


class ComplianceCheck:
    """Writes one audit entry per pick-wave release to the injected sink."""

    def __init__(self, sink, site):
        self._sink = sink
        self._site = site

    def record_release(self, wave_id, zone, kind, release_id):
        if not wave_id:
            raise ValueError("release record needs a wave id")
        entry = {
            "event": RELEASE_EVENT,
            "site": self._site,
            "wave_id": wave_id,
            "zone": zone,
            "kind": kind,
            "release_id": release_id,
        }
        self._sink.write(entry)
        return entry
