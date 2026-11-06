from coldchain.external_requester import process_queue
from coldchain.formatting import format_summary
from coldchain.models import ReleaseRequest
from coldchain.policy_client import build_payload, parse_decision

import pytest


def make_request(n, temperature_c=3.5):
    return ReleaseRequest(request_id=f"R-{n}", pallet_id=f"PAL-{n}", sku="VACC-02",
                          dock_door="D4", temperature_c=temperature_c, min_c=2.0, max_c=8.0)


class FakePolicy:
    def __init__(self, answers):
        self.answers = answers
        self.calls = []

    def __call__(self, payload, timeout):
        self.calls.append(payload["pallet_id"])
        answer = self.answers[payload["pallet_id"]]
        if answer == "timeout":
            raise TimeoutError("policy service did not answer")
        return {"decision": answer}


class FakeDock:
    def __init__(self):
        self.released = []

    def __call__(self, pallet_id, dock_door):
        self.released.append((pallet_id, dock_door))


def test_released_pallet_goes_to_its_door():
    dock = FakeDock()
    summary = process_queue([make_request(1)], FakePolicy({"PAL-1": "release"}), dock)
    assert dock.released == [("PAL-1", "D4")]
    assert summary["released"] == ["PAL-1"]


def test_denied_and_held_pallets_stay_in_staging():
    dock = FakeDock()
    policy = FakePolicy({"PAL-1": "deny", "PAL-2": "hold"})
    summary = process_queue([make_request(1), make_request(2)], policy, dock)
    assert dock.released == []
    assert summary["denied"] == ["PAL-1"]
    assert summary["held"] == ["PAL-2"]


def test_policy_timeout_does_not_abort_the_run():
    dock = FakeDock()
    policy = FakePolicy({"PAL-1": "release", "PAL-2": "timeout", "PAL-3": "release"})
    queue = [make_request(1), make_request(2), make_request(3)]
    summary = process_queue(queue, policy, dock)
    assert policy.calls == ["PAL-1", "PAL-2", "PAL-3"]
    assert ("PAL-3", "D4") in dock.released
    assert "PAL-1" in summary["released"] and "PAL-3" in summary["released"]


def test_payload_and_decision_parsing():
    payload = build_payload(make_request(7, temperature_c=4.0))
    assert payload["range_c"] == [2.0, 8.0]
    assert parse_decision({"decision": " Hold "}).value == "hold"
    with pytest.raises(ValueError):
        parse_decision({"decision": "maybe"})


def test_summary_format():
    assert format_summary({"released": ["a"], "held": [], "denied": ["b", "c"]}) == \
        "released=1, held=0, denied=2"
