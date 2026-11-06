from datetime import datetime, timedelta, timezone

import pytest

from livestream_flags import (Action, ActionRequest, ActionRequester, AuditNotifier,
                              ReviewDigest, RiskMonitor, Severity, StreamFlag)
from livestream_flags.formatting import format_duration, stream_label

T0 = datetime(2026, 3, 2, 18, 0, tzinfo=timezone.utc)


class ListSink:
    def __init__(self):
        self.sent = []

    def deliver(self, channel, payload):
        self.sent.append((channel, payload))


class Controller:
    def __init__(self):
        self.calls = []

    def keep_live(self, stream_id):
        self.calls.append(("keep_live", stream_id))

    def restart(self, stream_id):
        self.calls.append(("restart", stream_id))


def build(flags, requests):
    sink, controller, digest = ListSink(), Controller(), ReviewDigest()
    monitor = RiskMonitor(flags, AuditNotifier(sink), digest)
    return ActionRequester(requests, controller, monitor), controller, digest, sink


def test_unflagged_streams_are_applied_without_reports():
    req = [ActionRequest("r1", "s1", Action.KEEP_LIVE, T0),
           ActionRequest("r2", "s2", Action.RESTART, T0)]
    worker, controller, digest, _ = build({}, req)
    assert worker.process_queue() == ["r1", "r2"]
    assert controller.calls == [("keep_live", "s1"), ("restart", "s2")]
    assert digest.entries == []


def test_flag_inside_review_window_does_not_stop_the_queue():
    flags = {"s1": StreamFlag("s1", "graphic content", T0 + timedelta(hours=1))}
    req = [ActionRequest("r1", "s1", Action.KEEP_LIVE, T0),
           ActionRequest("r2", "s2", Action.RESTART, T0)]
    worker, controller, digest, _ = build(flags, req)
    assert worker.process_queue() == ["r1", "r2"]
    assert controller.calls == [("keep_live", "s1"), ("restart", "s2")]
    assert [r.request_id for r in digest.by_severity(Severity.WARNING)] == ["r1"]


def test_past_deadline_is_recorded_as_critical_in_digest():
    flags = {"s1": StreamFlag("s1", "graphic content", T0 - timedelta(minutes=5))}
    worker, _, digest, _ = build(flags, [ActionRequest("r1", "s1", Action.KEEP_LIVE, T0)])
    worker.process_queue()
    (report,) = digest.by_severity(Severity.CRITICAL)
    assert report.overdue_seconds == 300


def test_audit_notifier_rejects_non_critical_reports():
    from livestream_flags import RiskReport
    notifier = AuditNotifier(ListSink())
    with pytest.raises(ValueError):
        notifier.notify(RiskReport("r1", "s1", Severity.WARNING, "x"))


def test_audit_notifier_payload_format():
    from livestream_flags import RiskReport
    sink = ListSink()
    AuditNotifier(sink, channel="audit").notify(
        RiskReport("r1", "s1", Severity.CRITICAL, "late", overdue_seconds=3725))
    ((channel, payload),) = sink.sent
    assert channel == "audit"
    assert payload["severity"] == "critical"
    assert payload["overdue"] == "1h 02m 05s"


def test_formatting_helpers():
    assert format_duration(0) == "0s"
    assert format_duration(65) == "1m 05s"
    assert stream_label("abc") == "stream:abc"
