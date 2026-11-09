import pytest

from costwatch import (ActionGuard, AlertNotifier, BudgetEnvelope, ManagedClient, RateCard,
                       ResourceRequest, Severity)


class FakeChannel:
    def __init__(self):
        self.posts = []

    def post(self, recipient, payload):
        self.posts.append((recipient, payload))


class FakeProvisioner:
    def __init__(self):
        self.provisioned = []

    def provision(self, request):
        self.provisioned.append(request.request_id)


def make(limit=1000.0):
    envelope = BudgetEnvelope("acct-analytics", limit)
    guard = ActionGuard(envelope, RateCard(), AlertNotifier(FakeChannel()))
    provisioner = FakeProvisioner()
    return envelope, guard, ManagedClient(guard, provisioner), provisioner


def req(rid, instance_type="c6.xlarge", count=1, hours=100):
    return ResourceRequest(rid, "acct-analytics", instance_type, count, hours)


def test_quote_uses_rate_card():
    assert RateCard().quote(req("q-1", "c6.large", 2, 10)) == 1.7
    with pytest.raises(ValueError):
        RateCard().quote(req("q-2", "x9.huge"))


def test_request_within_budget_is_provisioned():
    envelope, guard, client, provisioner = make()
    outcome = client.submit(req("r-1"))
    assert outcome.provisioned
    assert provisioner.provisioned == ["r-1"]
    assert envelope.committed == 17.0
    assert guard.ledger == []


def test_request_over_budget_is_denied():
    envelope, guard, client, provisioner = make()
    outcome = client.submit(req("r-2", "g5.12xlarge", 2, 200))
    assert not outcome.provisioned
    assert provisioner.provisioned == []
    assert envelope.committed == 0.0


def test_warning_is_recorded_without_raising():
    envelope, guard, client, provisioner = make()
    decision = guard.review(req("r-3", "r6.4xlarge", 1, 850))
    assert decision.allowed
    assert decision.report.severity is Severity.WARNING
    assert [r.request_id for r in guard.warnings()] == ["r-3"]
    assert envelope.committed == pytest.approx(856.8)


def test_queue_keeps_draining_after_a_warning():
    envelope, guard, client, provisioner = make()
    outcomes = client.run([req("r-4"), req("r-5", "r6.4xlarge", 1, 800), req("r-6")])
    assert [o.provisioned for o in outcomes] == [True, True, True]
    assert client.provisioned_ids() == ["r-4", "r-5", "r-6"]
