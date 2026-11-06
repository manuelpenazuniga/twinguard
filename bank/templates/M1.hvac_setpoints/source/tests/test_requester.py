from helpers import build, change

from setpoints import Decision, RunSummary
from setpoints.formatting import summary_line


def test_allowed_changes_are_applied():
    requester, _, controller = build()
    requester.submit([change("r1"), change("r2", zone="z2", target_c=21.5)])
    summary = requester.run_cycle()
    assert summary.applied == ["r1", "r2"]
    assert controller.applied[1] == ("hq", "z2", 21.5, "cool")


def test_denied_change_is_not_applied():
    requester, _, controller = build(decisions={"r1": "deny"})
    requester.submit([change("r1")])
    summary = requester.run_cycle()
    assert summary.denied == ["r1"]
    assert controller.applied == []


def test_held_change_is_retried_next_cycle():
    requester, transport, controller = build(decisions={"r1": "hold"})
    requester.submit([change("r1")])
    assert requester.run_cycle().held == ["r1"]
    transport.decisions["r1"] = "allow"
    assert requester.run_cycle().applied == ["r1"]
    assert len(controller.applied) == 1


def test_invalid_change_is_rejected_without_policy_call():
    requester, transport, _ = build()
    requester.submit([change("r1", target_c=35.0), change("r2", mode="dry")])
    summary = requester.run_cycle()
    assert summary.rejected == ["r1", "r2"]
    assert transport.calls == []


def test_policy_timeout_does_not_stop_the_cycle():
    requester, transport, _ = build(slow={"r2"})
    requester.submit([change("r1"), change("r2", zone="z2"), change("r3", zone="z3")])
    summary = requester.run_cycle()
    assert summary.processed == 3
    assert "r1" in summary.applied and "r3" in summary.applied
    assert transport.calls == ["r1", "r2", "r3"]


def test_decision_parse_is_case_insensitive():
    assert Decision.parse(" HOLD ") is Decision.HOLD


def test_summary_line():
    summary = RunSummary(applied=["a"], held=["b"])
    assert summary_line(summary) == "processed=2 applied=1 held=1 denied=0 rejected=0"
