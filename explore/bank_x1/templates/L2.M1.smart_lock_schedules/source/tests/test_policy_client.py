import pytest

from lockops.models import ChangeKind, Decision, PolicyError, PolicyTimeout, ScheduleChange
from lockops.policy_client import DECISIONS_PATH, AccessPolicyClient


class FixedTransport:
    def __init__(self, response=None, timeout=False):
        self.response = response
        self.timeout = timeout
        self.seen = []

    def post(self, path, payload, timeout):
        self.seen.append((path, payload, timeout))
        if self.timeout:
            raise TimeoutError("slow")
        return self.response


CHANGE = ScheduleChange("c1", "bldg-7", "door-1", ChangeKind.RESTRICT, (), "facilities")


def test_decision_is_parsed():
    transport = FixedTransport({"decision": "hold"})
    client = AccessPolicyClient(transport, timeout_s=1.5)
    assert client.decide(CHANGE) is Decision.HOLD
    path, payload, timeout = transport.seen[0]
    assert path == DECISIONS_PATH
    assert payload["kind"] == "restrict"
    assert timeout == 1.5


def test_timeout_is_reported_as_policy_timeout():
    client = AccessPolicyClient(FixedTransport(timeout=True), timeout_s=0.5)
    with pytest.raises(PolicyTimeout) as info:
        client.decide(CHANGE)
    assert info.value.change_id == "c1"


@pytest.mark.parametrize("response", [None, {}, {"decision": "maybe"}])
def test_malformed_response_raises(response):
    with pytest.raises(PolicyError):
        AccessPolicyClient(FixedTransport(response)).decide(CHANGE)


def test_timeout_must_be_positive():
    with pytest.raises(ValueError):
        AccessPolicyClient(FixedTransport(), timeout_s=0)
