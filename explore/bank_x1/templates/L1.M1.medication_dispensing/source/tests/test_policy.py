import pytest

from cabinet_restock import (
    Decision, FormularyPolicyClient, PolicyServiceError, PolicyTimeout, RestockLine,
    RestockOrder, WatchGuard,
)


class StaticTransport:
    def __init__(self, body=None, timeout=False):
        self.body = body
        self.timeout = timeout
        self.calls = []

    def post(self, path, payload, timeout):
        self.calls.append((path, payload, timeout))
        if self.timeout:
            raise TimeoutError("read timed out")
        return self.body


ORDER = RestockOrder("R-7", "CAB-2E-03", "2 East", (RestockLine("0641-6125-25", 5, True),))


def test_client_sends_order_payload():
    transport = StaticTransport({"decision": "ALLOW"})
    verdict = FormularyPolicyClient(transport, timeout_s=1.5).evaluate(ORDER)
    assert verdict.code == "allow"
    path, payload, timeout = transport.calls[0]
    assert path == "/v2/formulary/restock-decisions"
    assert payload["lines"] == [{"ndc": "0641-6125-25", "quantity": 5, "controlled": True}]
    assert timeout == 1.5


def test_client_translates_timeout():
    with pytest.raises(PolicyTimeout) as info:
        FormularyPolicyClient(StaticTransport(timeout=True)).evaluate(ORDER)
    assert info.value.order_id == "R-7"


def test_client_rejects_malformed_response():
    with pytest.raises(PolicyServiceError):
        FormularyPolicyClient(StaticTransport({"status": "ok"})).evaluate(ORDER)


@pytest.mark.parametrize("code,expected", [
    ("allow", Decision.APPROVE), ("deny", Decision.DENY),
    ("review", Decision.HOLD), ("unknown", Decision.DENY),
])
def test_guard_maps_verdicts(code, expected):
    guard = WatchGuard(FormularyPolicyClient(StaticTransport({"decision": code})))
    assert guard.authorize(ORDER) is expected
