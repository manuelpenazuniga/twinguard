from conftest import StubTransport, make_change

from setpoints import (
    ActionAuditor,
    ActionRequester,
    BmsGateway,
    Decision,
    EnergyPolicyClient,
)


def build(answers, bms):
    transport = StubTransport(answers)
    auditor = ActionAuditor(EnergyPolicyClient(transport, timeout_s=0.5))
    return ActionRequester(auditor, BmsGateway(bms)), transport


def test_allowed_change_is_written(bms):
    requester, _ = build({"c1": "allow"}, bms)
    report = requester.run([make_change("c1", target_c=22.3)])
    assert report.applied == ["c1"]
    assert bms.writes == [("hq/z1/heat-setpoint", 22.5)]


def test_denied_and_held_changes_are_not_written(bms):
    requester, _ = build({"c1": "deny", "c2": "hold"}, bms)
    report = requester.run([make_change("c1"), make_change("c2")])
    assert report.denied == ["c1"]
    assert report.held == ["c2"]
    assert bms.writes == []


def test_out_of_range_target_never_reaches_policy_service(bms):
    requester, transport = build({"c1": "allow"}, bms)
    report = requester.run([make_change("c1", target_c=31.0, current_c=29.0)])
    assert report.denied == ["c1"]
    assert transport.requests == []
    assert bms.writes == []


def test_run_completes_when_policy_times_out(bms):
    answers = {"c1": "allow", "c2": "timeout", "c3": "allow"}
    requester, transport = build(answers, bms)
    queue = [make_change("c1", zone="z1"), make_change("c2", zone="z2"),
             make_change("c3", zone="z3")]
    report = requester.run(queue)
    assert report.processed == 3
    assert "c1" in report.applied and "c3" in report.applied
    assert [cid for _, cid in transport.requests] == ["c1", "c2", "c3"]
    assert len(requester.log) == 3


def test_log_line_mentions_decision(bms):
    requester, _ = build({"c1": "hold"}, bms)
    requester.run([make_change("c1")])
    assert requester.log[0].startswith(Decision.HOLD.value)
    assert "hq/z1" in requester.log[0]
