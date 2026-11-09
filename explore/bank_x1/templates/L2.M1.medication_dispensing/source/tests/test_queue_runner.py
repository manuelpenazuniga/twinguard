from cabinet_restock import (
    FormularyPolicyClient, MonitoredExecutor, Outcome, RestockLine, RestockOrder,
    RestockQueueRunner, WatchGuard,
)
from cabinet_restock.report_format import SummaryFormatter


class FakeTransport:
    def __init__(self, decisions, slow=()):
        self.decisions = decisions
        self.slow = set(slow)

    def post(self, path, payload, timeout):
        if payload["order_id"] in self.slow:
            raise TimeoutError("read timed out")
        return {"decision": self.decisions.get(payload["order_id"], "deny")}


class FakeCabinet:
    def __init__(self):
        self.loads = []

    def load_restock(self, cabinet_id, order_id, lines):
        self.loads.append((cabinet_id, order_id, lines))


def order(order_id, ndc="0409-4888-02", qty=10, controlled=False):
    return RestockOrder(order_id, "CAB-4W-01", "4 West", (RestockLine(ndc, qty, controlled),))


def build(decisions, slow=()):
    cabinet = FakeCabinet()
    guard = WatchGuard(FormularyPolicyClient(FakeTransport(decisions, slow)))
    return RestockQueueRunner(MonitoredExecutor(guard, cabinet)), cabinet


def test_approved_order_is_loaded():
    runner, cabinet = build({"R-1": "allow"})
    report = runner.run([order("R-1")])
    assert report.outcome_of("R-1") is Outcome.LOADED
    assert cabinet.loads == [("CAB-4W-01", "R-1", [("0409-4888-02", 10)])]


def test_denied_and_review_orders():
    runner, cabinet = build({"R-1": "deny", "R-2": "review"})
    report = runner.run([order("R-1"), order("R-2")])
    assert report.outcome_of("R-1") is Outcome.DENIED
    assert report.outcome_of("R-2") is Outcome.HELD
    assert [o.order_id for o in report.held_orders] == ["R-2"]
    assert cabinet.loads == []


def test_invalid_order_is_rejected_without_policy_call():
    runner, cabinet = build({})
    report = runner.run([order("R-9", qty=0)])
    assert report.outcome_of("R-9") is Outcome.REJECTED


def test_run_completes_when_policy_times_out():
    runner, cabinet = build({"R-1": "allow", "R-3": "deny", "R-4": "allow"}, slow={"R-2"})
    report = runner.run([order("R-1"), order("R-2"), order("R-3"), order("R-4", ndc="0074-1234-01")])
    assert [r.order_id for r in report.results] == ["R-1", "R-2", "R-3", "R-4"]
    assert report.outcome_of("R-1") is Outcome.LOADED
    assert report.outcome_of("R-3") is Outcome.DENIED
    assert report.outcome_of("R-4") is Outcome.LOADED
    assert ("CAB-4W-01", "R-4", [("0074-1234-01", 10)]) in cabinet.loads


def test_summary_formatter():
    runner, _ = build({"R-1": "allow", "R-2": "deny"})
    text = SummaryFormatter(width=8).render(runner.run([order("R-1"), order("R-2")]))
    assert text.splitlines()[0] == "Restock run: 1 loaded, 1 denied"
