from suspensions.accounts import AccountsGateway
from suspensions.audit import ControlMonitor
from suspensions.executor import MonitoredExecutor
from suspensions.models import AccountState, Action, OutcomeStatus, SuspensionRequest
from suspensions.policy import SuspensionPolicy


class ListSink:
    def __init__(self):
        self.events = []

    def emit(self, event):
        self.events.append(event)


def make(accounts):
    gateway = AccountsGateway(accounts)
    executor = MonitoredExecutor(
        gateway,
        SuspensionPolicy(protected_accounts={"acct-staff-1"}),
        ControlMonitor(ListSink()),
    )
    return gateway, executor


def req(rid, account, action, reason="repeated spam reports", case_ref=""):
    return SuspensionRequest(rid, account, action, reason, case_ref)


def test_suspension_goes_through_gateway():
    gateway, executor = make({"acct-1": "active"})
    outcome = executor.process(req("r-1", "acct-1", Action.SUSPEND))
    assert outcome.status is OutcomeStatus.APPLIED
    assert outcome.change_id and outcome.change_id.startswith("chg-")
    assert gateway.state_of("acct-1") is AccountState.SUSPENDED


def test_reinstatement_goes_through_gateway():
    gateway, executor = make({"acct-2": "suspended"})
    outcome = executor.process(req("r-2", "acct-2", Action.REINSTATE, "appeal upheld by reviewer"))
    assert outcome.status is OutcomeStatus.APPLIED
    assert gateway.state_of("acct-2") is AccountState.ACTIVE
    assert "reinstated" in outcome.notice


def test_already_suspended_account_is_unchanged():
    gateway, executor = make({"acct-3": "suspended"})
    outcome = executor.process(req("r-3", "acct-3", Action.SUSPEND, case_ref="CASE-77"))
    assert outcome.status is OutcomeStatus.UNCHANGED
    assert outcome.change_id is not None
    assert outcome.notice.endswith("CASE-77.")


def test_protected_account_is_rejected():
    gateway, executor = make({"acct-staff-1": "active"})
    outcome = executor.process(req("r-4", "acct-staff-1", Action.SUSPEND))
    assert outcome.status is OutcomeStatus.REJECTED
    assert gateway.state_of("acct-staff-1") is AccountState.ACTIVE


def test_run_processes_queue_in_order():
    gateway, executor = make({"acct-5": "active", "acct-6": "suspended"})
    outcomes = executor.run([
        req("r-5", "acct-5", Action.SUSPEND),
        req("r-6", "acct-6", Action.REINSTATE, "appeal upheld by reviewer"),
        req("r-7", "acct-5", Action.REINSTATE, "short"),
    ])
    assert [o.request_id for o in outcomes] == ["r-5", "r-6", "r-7"]
    assert [o.status for o in outcomes] == [
        OutcomeStatus.APPLIED, OutcomeStatus.APPLIED, OutcomeStatus.REJECTED]
    assert gateway.state_of("acct-5") is AccountState.SUSPENDED
