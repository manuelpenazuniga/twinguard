import pytest

from acl.formatting import format_result, summarize
from acl.requests import InvalidRequest, parse_request
from acl.upstream_worker import process_requests


class FakeControlPlane:
    """In-memory control plane that only honours the v2 access API."""

    def __init__(self, public=()):
        self.public_read = {name: True for name in public}
        self.calls = []
        self._next = 1

    def call(self, operation, params):
        self.calls.append((operation, params))
        if operation == "PutBucketAcl":
            # Retired: accepted for compatibility, no effect.
            return {"Deprecated": True}
        if operation == "PutPublicAccessConfig":
            bucket = params["Bucket"]
            wanted = params["PublicAccess"]["Read"]
            status = "Unchanged" if self.public_read.get(bucket, False) == wanted else "Applied"
            self.public_read[bucket] = wanted
            change_id = f"chg-{self._next:04d}"
            self._next += 1
            return {"ChangeId": change_id, "Status": status}
        return {"Error": {"Code": "UnknownOperation", "Message": operation}}


def allow_all(change):
    return True


def ignore_events(event):
    pass


def msg(rid, bucket, public):
    return {"id": rid, "bucket": bucket, "public": public, "requested_by": "team-media"}


def test_grant_makes_bucket_public():
    plane = FakeControlPlane()
    [result] = process_requests([msg("r1", "media-thumbs", True)], plane, allow_all, ignore_events)
    assert result["status"] == "applied"
    assert plane.public_read["media-thumbs"] is True
    assert result["change_id"].startswith("chg-")


def test_revoke_makes_bucket_private():
    plane = FakeControlPlane(public=["old-assets"])
    [result] = process_requests([msg("r2", "old-assets", False)], plane, allow_all, ignore_events)
    assert result["status"] == "applied"
    assert plane.public_read["old-assets"] is False


def test_unchanged_bucket_is_reported_as_applied():
    plane = FakeControlPlane(public=["static-site"])
    [result] = process_requests([msg("r3", "static-site", True)], plane, allow_all, ignore_events)
    assert result["status"] == "applied"
    assert result["change_id"] is not None


def test_denied_request_is_not_sent():
    plane = FakeControlPlane()
    results = process_requests([msg("r4", "payroll-exports", True)], plane,
                               lambda change: False, ignore_events)
    assert results[0]["status"] == "denied"
    assert plane.calls == []


def test_invalid_message_is_reported():
    plane = FakeControlPlane()
    [result] = process_requests([{"id": "r5", "bucket": "Bad_Name", "public": True,
                                  "requested_by": "x"}], plane, allow_all, ignore_events)
    assert result["status"] == "invalid"
    assert plane.calls == []


@pytest.mark.parametrize("message", [
    {"id": "r", "bucket": "ok-bucket", "public": "yes", "requested_by": "x"},
    {"id": "r", "bucket": "a..b", "public": True, "requested_by": "x"},
    {"bucket": "ok-bucket", "public": True, "requested_by": "x"},
])
def test_parse_request_rejects(message):
    with pytest.raises(InvalidRequest):
        parse_request(message)


def test_summary_formatting():
    results = [
        {"request_id": "r1", "bucket": "a-b", "status": "applied", "change_id": "chg-1"},
        {"request_id": "r2", "bucket": "c-d", "status": "denied", "change_id": None},
    ]
    assert format_result(results[0]) == "r1 a-b applied (chg-1)"
    assert summarize(results) == "applied=1, denied=1"
    assert summarize([]) == "no requests"
