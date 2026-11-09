import pytest

from fulfillment.action_requester import parse_request
from fulfillment.decisions import Decision
from fulfillment.reporting import format_amount
from fulfillment.risk_monitor import build_policy_payload, evaluate_release


def make_request(**overrides):
    entry = {"order_id": "HV-1", "customer_id": "C-9", "amount_cents": 320_000,
             "currency": "eur", "ship_to_country": "de"}
    entry.update(overrides)
    return parse_request(entry)


@pytest.mark.parametrize("verdict,expected", [
    ("approve", Decision.RELEASE),
    ("REVIEW", Decision.HOLD),
    ("reject", Decision.DENY),
    ("something-new", Decision.HOLD),
])
def test_verdict_mapping(verdict, expected):
    assert evaluate_release(make_request(), lambda payload, timeout_s: verdict) is expected


def test_payload_fields():
    payload = build_policy_payload(make_request(address_changed=True))
    assert payload["currency"] == "EUR"
    assert payload["ship_to_country"] == "DE"
    assert payload["address_changed"] is True


def test_parse_request_rejects_missing_fields():
    with pytest.raises(ValueError):
        parse_request({"order_id": "HV-2", "amount_cents": 100})


def test_format_amount():
    assert format_amount(123_456, "USD") == "$1,234.56"
    assert format_amount(5_000, "CHF") == "50.00 CHF"
