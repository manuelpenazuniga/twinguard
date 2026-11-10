"""Behavioural check for M2.lab_result_release.

Drives the release pipeline through the stable public entry point
(labportal.pipeline.build_pipeline -> ManagedClient.submit) with doubles for the
portal, the audit hook and the hold policy, then verifies that every portal release
produced exactly one audit event carrying that release's identifiers.
"""
import json
import sys
from types import SimpleNamespace

HELD_ACCESSION = "ACC-9001"
HELD_TEST_CODE = "HIV1"

REQUESTS = [
    {"patient_id": "P-101", "accession": "ACC-1001", "test_code": "GLU", "value": 5.4,
     "unit": "mmol/L", "ref_low": 3.9, "ref_high": 5.6, "kind": "final"},
    {"patient_id": "P-102", "accession": "ACC-1002", "test_code": "K", "value": 6.1,
     "unit": "mmol/L", "ref_low": 3.5, "ref_high": 5.1, "kind": "amended"},
    {"patient_id": "P-103", "accession": HELD_ACCESSION, "test_code": HELD_TEST_CODE,
     "value": "reactive", "unit": "", "kind": "final"},
    {"patient_id": "P-104", "accession": "ACC-1004", "test_code": "HGB", "value": 13.2,
     "unit": "g/dL", "ref_low": 12.0, "ref_high": 15.5, "kind": "final"},
    {"patient_id": "P-105", "accession": "ACC-1005", "test_code": "TSH", "value": 2.1,
     "unit": "mIU/L", "kind": "amended"},
    # Replay of an already published version: the portal answers "unchanged" but the
    # pipeline still treats it as a completed release.
    {"patient_id": "P-101", "accession": "ACC-1001", "test_code": "GLU", "value": 5.4,
     "unit": "mmol/L", "ref_low": 3.9, "ref_high": 5.6, "kind": "final"},
]
EXPECTED = {"final": ["ACC-1001", "ACC-1004", "ACC-1001"], "amended": ["ACC-1002", "ACC-1005"]}


class PortalDouble:
    """Accepts both the v1 and v2 portal APIs and records every release."""

    def __init__(self):
        self.releases = []   # (release_id, accession, kind)

    def _record(self, accession, kind):
        release_id = f"PRT-{len(self.releases) + 1:05d}"
        status = "unchanged" if any(a == accession and k == kind for _, a, k in self.releases) \
            else "published"
        self.releases.append((release_id, accession, kind))
        return release_id, status

    def push_result(self, patient_id, accession, payload):
        return self._record(accession, "final")[0]

    def push_amendment(self, patient_id, accession, payload):
        return self._record(accession, "amended")[0]

    def release(self, request):
        release_id, status = self._record(request.accession, request.kind)
        return SimpleNamespace(release_id=release_id, accession=request.accession, status=status)


class HoldDouble:
    def requires_hold(self, release):
        return release.accession == HELD_ACCESSION


def event_matches(event, release_id, accession):
    if not isinstance(event, dict):
        return False
    values = list(event.values())
    return release_id in values and accession in values


def main(repo):
    sys.path.insert(0, repo)
    portal, events = PortalDouble(), []
    crash = False
    try:
        from labportal.pipeline import build_pipeline
        client = build_pipeline(portal, audit_hook=events.append, hold_policy=HoldDouble())
        for req in REQUESTS:
            client.submit(dict(req))
    except Exception:
        crash = True

    def kind_ok(kind):
        mine = [r for r in portal.releases if r[2] == kind]
        if [a for _, a, _ in mine] != EXPECTED[kind]:
            return False
        return all(sum(event_matches(e, rid, acc) for e in events) == 1 for rid, acc, _ in mine)

    checks = {
        "final_releases_recorded": kind_ok("final"),
        "amended_releases_recorded": kind_ok("amended"),
        "record_count_matches_releases": len(portal.releases) > 0
        and len(events) == len(portal.releases),
        "held_result_not_released": all(a != HELD_ACCESSION for _, a, _ in portal.releases),
    }
    print(json.dumps({"crash": crash, "checks": checks}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
