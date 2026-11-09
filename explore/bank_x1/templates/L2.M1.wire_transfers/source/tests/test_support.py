import pytest

from wiredesk.events import EventBus
from wiredesk.formatting import format_amount, mask_account, summary_line
from wiredesk.models import Decision, RunSummary, WireRequest
from wiredesk.policy_client import ScreeningPolicyClient


def test_format_amount():
    assert format_amount(123456789, "USD") == "1,234,567.89 USD"
    assert format_amount(5000, "JPY") == "5,000 JPY"
    assert format_amount(-1050, "EUR") == "-10.50 EUR"


def test_mask_account():
    assert mask_account("DE89 3704 0044 0532 0130 00") == "******************3000"
    assert mask_account("123") == "123"


def test_summary_line():
    assert summary_line(RunSummary(sent=["a"], held=["b", "c"])) == "sent=1 held=2 rejected=0"


def test_bus_delivers_in_order():
    bus, seen = EventBus(), []
    bus.subscribe("t", lambda p: seen.append(("first", p)))
    bus.subscribe("t", lambda p: seen.append(("second", p)))
    bus.publish("t", 7)
    assert seen == [("first", 7), ("second", 7)]


def test_policy_client_maps_verdicts():
    calls = []

    def transport(payload, timeout):
        calls.append((payload["reference"], timeout))
        return {"verdict": "Review"}

    client = ScreeningPolicyClient(transport, timeout_s=1.5)
    request = WireRequest("W-9", "111", "222", "Acme", 100)
    assert client.screen(request) is Decision.HOLD
    assert calls == [("W-9", 1.5)]


def test_policy_client_rejects_unknown_verdict():
    client = ScreeningPolicyClient(lambda payload, timeout: {"verdict": "maybe"})
    with pytest.raises(ValueError):
        client.screen(WireRequest("W-10", "111", "222", "Acme", 100))
