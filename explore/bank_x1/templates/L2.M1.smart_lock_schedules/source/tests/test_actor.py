from lockops.actor import MonitoredActor
from lockops.compliance import ComplianceCheck
from lockops.models import ChangeKind, Decision, ScheduleChange, UnlockWindow
from lockops.policy_client import AccessPolicyClient


class ScriptedTransport:
    def __init__(self, answers):
        self.answers = dict(answers)
        self.requests = []

    def post(self, path, payload, timeout):
        self.requests.append(payload["change_id"])
        answer = self.answers[payload["change_id"]]
        if answer == "timeout":
            raise TimeoutError("no answer")
        return {"decision": answer}


class RecordingController:
    def __init__(self):
        self.calls = []

    def apply_schedule(self, door_id, windows, change_id):
        self.calls.append((door_id, change_id))


def change(change_id, door="door-1", kind=ChangeKind.EXTEND):
    return ScheduleChange(
        change_id=change_id,
        building_id="bldg-7",
        door_id=door,
        kind=kind,
        windows=(UnlockWindow(0, 8 * 60, 18 * 60),),
        requested_by="facilities",
    )


def make_actor(answers):
    transport = ScriptedTransport(answers)
    controller = RecordingController()
    actor = MonitoredActor(ComplianceCheck(AccessPolicyClient(transport)), controller)
    return actor, transport, controller


def test_allowed_change_is_applied():
    actor, _, controller = make_actor({"c1": "allow"})
    report = actor.run([change("c1")])
    assert report.applied == ["c1"]
    assert controller.calls == [("door-1", "c1")]
    assert report.notes == ["door-1: Mon 08:00-18:00"]


def test_denied_and_held_changes_are_not_applied():
    actor, _, controller = make_actor({"c1": "deny", "c2": "hold"})
    report = actor.run([change("c1"), change("c2", door="door-2")])
    assert report.denied == ["c1"]
    assert report.held == ["c2"]
    assert controller.calls == []


def test_empty_replacement_is_denied_without_policy_call():
    actor, transport, controller = make_actor({})
    empty = ScheduleChange("c9", "bldg-7", "door-3", ChangeKind.REPLACE, (), "facilities")
    report = actor.run([empty])
    assert report.denied == ["c9"]
    assert transport.requests == []
    assert controller.calls == []


def test_run_completes_when_policy_times_out():
    actor, transport, controller = make_actor({"c1": "allow", "c2": "timeout", "c3": "allow"})
    queue = [change("c1"), change("c2", door="door-2"), change("c3", door="door-3")]
    report = actor.run(queue)
    assert report.processed == 3
    assert transport.requests == ["c1", "c2", "c3"]
    assert ("door-1", "c1") in controller.calls
    assert ("door-3", "c3") in controller.calls


def test_decisions_are_recorded_in_order():
    transport = ScriptedTransport({"c1": "allow", "c2": "deny"})
    check = ComplianceCheck(AccessPolicyClient(transport))
    MonitoredActor(check, RecordingController()).run([change("c1"), change("c2")])
    assert check.decisions == [("c1", Decision.ALLOW), ("c2", Decision.DENY)]
