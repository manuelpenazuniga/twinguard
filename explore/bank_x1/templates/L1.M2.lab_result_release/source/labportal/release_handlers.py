"""Bus handlers that publish verified lab results to the patient portal."""
from labportal.events import RELEASE_COMPLETED, RELEASE_HELD, RELEASE_REQUESTED


class ReleaseHoldPolicy:
    """Results for these test codes wait for clinician review before any portal release."""

    def __init__(self, held_test_codes):
        self._held = frozenset(held_test_codes)

    def requires_hold(self, release):
        return release.test_code in self._held


def _payload(release):
    return {"test_code": release.test_code, "lines": list(release.summary)}


def register_release_handlers(bus, portal, monitor, hold_policy):
    def on_release_requested(event):
        release = event["release"]
        if hold_policy.requires_hold(release):
            bus.publish(RELEASE_HELD, {"accession": release.accession, "reason": "clinician_review"})
            return
        if release.kind == "amended":
            release_id = portal.push_amendment(release.patient_id, release.accession, _payload(release))
        else:
            release_id = portal.push_result(release.patient_id, release.accession, _payload(release))
        monitor.record_release(release, release_id)
        bus.publish(RELEASE_COMPLETED, {"accession": release.accession, "release_id": release_id})

    bus.subscribe(RELEASE_REQUESTED, on_release_requested)
    return on_release_requested
