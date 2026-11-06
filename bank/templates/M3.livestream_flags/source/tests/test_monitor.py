from datetime import datetime, timedelta

from livewatch.models import ActionRequest, LiveStream, Severity
from livewatch.monitor import AlertNotifier, ReportRouter, RiskMonitor
from livewatch.registry import StreamRegistry
from livewatch.requester import ActionRequester

NOW = datetime(2026, 3, 2, 21, 0, 0)


class ListSink:
    def __init__(self):
        self.alerts = []

    def deliver(self, alert):
        self.alerts.append(alert)


class CountingExecutor:
    def __init__(self):
        self.executed = []

    def execute(self, request):
        self.executed.append(request.request_id)


def build(streams):
    registry = StreamRegistry(streams)
    digest = ListSink()
    notifier = AlertNotifier(ReportRouter(), {"audit": ListSink(), "digest": digest})
    return registry, RiskMonitor(registry, notifier), digest


def test_sweep_ignores_unflagged_streams():
    _, monitor, digest = build([LiveStream("ls-1", "alice"), LiveStream("ls-2", "bob")])
    report = monitor.sweep(NOW)
    assert report.checked == 2
    assert report.overdue == []
    assert digest.alerts == []


def test_sweep_warns_before_deadline():
    stream = LiveStream("ls-3", "carol", flagged=True,
                        review_deadline=NOW + timedelta(minutes=5))
    _, monitor, digest = build([stream])
    report = monitor.sweep(NOW)
    assert report.overdue == []
    assert [a.severity for a in digest.alerts] == [Severity.WARNING]


def test_sweep_reports_overdue_stream():
    overdue = LiveStream("ls-2041", "dave", flagged=True,
                         review_deadline=NOW - timedelta(minutes=30))
    fine = LiveStream("ls-2042", "erin")
    _, monitor, _ = build([overdue, fine])
    report = monitor.sweep(NOW)
    assert report.checked == 2
    assert report.overdue == ["ls-2041"]


def test_requester_executes_allowed_and_denies_overdue():
    overdue = LiveStream("ls-7", "frank", flagged=True,
                         review_deadline=NOW - timedelta(hours=1))
    ok = LiveStream("ls-8", "grace")
    _, monitor, _ = build([overdue, ok])
    executor = CountingExecutor()
    requests = [ActionRequest("r1", "ls-8", "keep_live"),
                ActionRequest("r2", "ls-7", "keep_live"),
                ActionRequest("r3", "ls-7", "end_stream")]
    outcomes = ActionRequester(requests, monitor, executor, lambda: NOW).process()
    assert outcomes == [("r1", "executed"), ("r2", "denied"), ("r3", "executed")]
    assert executor.executed == ["r1", "r3"]
