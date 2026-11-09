from broadcasts.app import build_pipeline
from broadcasts.executor import BroadcastJob
from broadcasts.formatting import MAX_BODY_CHARS


class FakeTransport:
    def __init__(self):
        self.sent = []

    def send(self, audience, subject, body):
        self.sent.append((audience, subject, body))


class FakeNotifier:
    def __init__(self):
        self.sent = []

    def send(self, channel, payload):
        self.sent.append((channel, payload))


class FakeApprovals:
    def __init__(self, records):
        self.records = records

    def lookup(self, approval_id):
        return self.records.get(approval_id)


def make_job(job_id, body="Scheduled maintenance on the billing portal.", approval_id=None):
    return BroadcastJob(job_id=job_id, submitted_by="queue-worker", audience="customers-eu",
                        kind="maintenance", title="Billing portal", body=body,
                        approval_id=approval_id)


def make_pipeline(approvals=None):
    transport, notifier = FakeTransport(), FakeNotifier()
    pipeline = build_pipeline(transport, notifier, FakeApprovals(approvals or {}))
    return pipeline, transport, notifier


def test_approved_job_is_delivered_without_findings():
    pipeline, transport, notifier = make_pipeline(
        {"apr-1": {"job_id": "job-1", "approver": "ops-lead"}})
    assert pipeline.run([make_job("job-1", approval_id="apr-1")]) == ["job-1"]
    assert transport.sent[0][0] == "customers-eu"
    assert pipeline.monitor.journal == []
    assert notifier.sent == []


def test_oversized_notice_is_delivered_with_warning():
    approvals = {"apr-2": {"job_id": "job-2", "approver": "ops-lead"},
                 "apr-3": {"job_id": "job-3", "approver": "ops-lead"}}
    pipeline, transport, _ = make_pipeline(approvals)
    long_body = "word " * (MAX_BODY_CHARS // 2)
    queue = [make_job("job-2", body=long_body, approval_id="apr-2"),
             make_job("job-3", approval_id="apr-3")]
    assert pipeline.run(queue) == ["job-2", "job-3"]
    assert len(transport.sent[0][2]) <= MAX_BODY_CHARS
    warnings = pipeline.monitor.findings("warning")
    assert [(r.job_id, r.rule) for r in warnings] == [("job-2", "body-truncated")]


def test_mismatched_approval_is_journaled_as_critical():
    pipeline, _, _ = make_pipeline({"apr-9": {"job_id": "job-8", "approver": "ops-lead"}})
    pipeline.run([make_job("job-4", approval_id="apr-9")])
    assert [r.rule for r in pipeline.monitor.findings("critical")] == ["approval-mismatch"]
