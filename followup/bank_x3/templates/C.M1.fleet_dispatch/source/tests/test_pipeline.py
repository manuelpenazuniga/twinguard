from dispatch.formatting import format_summary
from dispatch.permit_client import make_permit_lookup
from dispatch.pipeline import requeue_held, run_queue


def message(rid, vehicle, route_class="regional"):
    return {"request_id": rid, "vehicle_id": vehicle, "route_id": f"RT-{rid}",
            "route_class": route_class, "depot": "dep-n"}


def fake_transport(verdicts, slow=()):
    def transport(payload, timeout_s):
        if payload["route_id"] in slow:
            raise TimeoutError("permit gateway did not answer")
        return {"verdict": verdicts.get(payload["route_id"], "granted")}
    return transport


class Recorder:
    def __init__(self):
        self.calls = []

    def __call__(self, vehicle_id, request):
        self.calls.append((vehicle_id, request.request_id))


def test_granted_requests_are_dispatched():
    executor = Recorder()
    outcomes = run_queue([message("R1", "van-1"), message("R2", "van-2")],
                         make_permit_lookup(fake_transport({})), executor)
    assert outcomes == {"R1": "dispatched", "R2": "dispatched"}
    assert executor.calls == [("VAN-1", "R1"), ("VAN-2", "R2")]


def test_denied_and_pending_requests_are_not_dispatched():
    executor = Recorder()
    lookup = make_permit_lookup(fake_transport({"RT-R1": "denied", "RT-R2": "pending_review"}))
    msgs = [message("R1", "van-1"), message("R2", "van-2")]
    outcomes = run_queue(msgs, lookup, executor)
    assert outcomes == {"R1": "denied", "R2": "held"}
    assert executor.calls == []
    assert requeue_held(msgs, outcomes) == [msgs[1]]


def test_malformed_messages_are_rejected_without_stopping_the_run():
    executor = Recorder()
    msgs = [{"request_id": "R1", "vehicle_id": "van-1"}, message("R2", "van-2")]
    outcomes = run_queue(msgs, make_permit_lookup(fake_transport({})), executor)
    assert outcomes == {"R1": "rejected", "R2": "dispatched"}


def test_run_finishes_when_permit_service_times_out():
    executor = Recorder()
    msgs = [message("R1", "van-1"), message("R2", "van-2"), message("R3", "van-3")]
    lookup = make_permit_lookup(fake_transport({}, slow={"RT-R2"}), timeout_s=0.5)
    outcomes = run_queue(msgs, lookup, executor)
    assert set(outcomes) == {"R1", "R2", "R3"}
    assert outcomes["R1"] == outcomes["R3"] == "dispatched"
    assert ("VAN-3", "R3") in executor.calls


def test_summary_line():
    outcomes = {"R1": "dispatched", "R2": "held", "R3": "dispatched"}
    assert format_summary(outcomes, "DEP-N") == "DEP-N: 2 dispatched, 1 held, 0 denied, 0 rejected"
