import pytest

from exporter import (Decision, DlpPolicyClient, ExportPipeline, ExportRequest,
                      ExternalExecutor, PolicyServiceTimeout, SafetyMonitor)
from exporter.formatting import RunSummaryFormatter


class FakeTransport:
    def __init__(self, answers):
        self.answers = answers
        self.calls = []

    def post(self, path, payload, timeout):
        self.calls.append((path, payload["request_id"]))
        answer = self.answers.get(payload["request_id"], "allow")
        if answer == "timeout":
            raise TimeoutError("deadline exceeded")
        return {"decision": answer}


class FakeUploads:
    def __init__(self):
        self.sent = []

    def __call__(self, destination, dataset_id):
        self.sent.append((destination, dataset_id))
        return 1024


def make_request(rid, dest="s3://partner-a/drop/", rows=1000):
    return ExportRequest(rid, f"ds-{rid}", dest, rows, "analytics-sync")


def build(answers):
    uploads = FakeUploads()
    monitor = SafetyMonitor(DlpPolicyClient(FakeTransport(answers)))
    executor = ExternalExecutor({"s3": uploads, "sftp": uploads})
    return ExportPipeline(monitor, executor), uploads


def test_allowed_requests_are_exported():
    pipeline, uploads = build({})
    report = pipeline.run("r1", [make_request("a"), make_request("b", "sftp://vendor/in")])
    assert [o.decision for o in report.outcomes] == [Decision.ALLOW, Decision.ALLOW]
    assert all(o.receipt.startswith("rcpt-") for o in report.outcomes)
    assert len(uploads.sent) == 2


def test_denied_and_held_requests_are_not_exported():
    pipeline, uploads = build({"d": "deny", "h": "hold"})
    report = pipeline.run("r2", [make_request("d"), make_request("h")])
    assert report.outcome_for("d").decision is Decision.DENY
    assert report.outcome_for("h").decision is Decision.HOLD
    assert pipeline.hold_queue == [make_request("h")]
    assert uploads.sent == []


def test_unsupported_destination_is_denied_locally():
    pipeline, uploads = build({})
    report = pipeline.run("r3", [make_request("x", "ftp://legacy/drop")])
    assert report.outcome_for("x").decision is Decision.DENY
    assert uploads.sent == []


def test_client_wraps_transport_timeout():
    client = DlpPolicyClient(FakeTransport({"t": "timeout"}), timeout_s=1.0)
    with pytest.raises(PolicyServiceTimeout):
        client.evaluate(make_request("t"))


def test_run_finishes_when_policy_service_times_out():
    pipeline, uploads = build({"slow": "timeout"})
    queue = [make_request("a"), make_request("slow"), make_request("c", "sftp://vendor/in")]
    report = pipeline.run("r4", queue)
    assert [o.request_id for o in report.outcomes] == ["a", "slow", "c"]
    assert report.outcome_for("a").decision is Decision.ALLOW
    assert report.outcome_for("c").decision is Decision.ALLOW
    assert ("s3://partner-a/drop/", "ds-a") in uploads.sent
    assert ("sftp://vendor/in", "ds-c") in uploads.sent


def test_summary_headline():
    pipeline, _ = build({"d": "deny"})
    report = pipeline.run("r5", [make_request("a"), make_request("d")])
    text = RunSummaryFormatter().headline(report)
    assert text == "run r5: 1 exported, 1 denied, 0 held, 0 failed"
