import pytest

from erasure.policy import check_eligibility
from erasure.requests import parse_request


def make(**overrides):
    data = {"request_id": "r-1", "customer_id": "c-1", "tables": "customers, addresses",
            "reason": "gdpr_art17", "identity_verified": True}
    data.update(overrides)
    return parse_request(data)


def test_parse_splits_and_sorts_tables():
    assert make().tables == ("addresses", "customers")


def test_parse_rejects_missing_fields():
    with pytest.raises(ValueError):
        parse_request({"request_id": "r-1"})


def test_policy_allows_verified_request():
    assert check_eligibility(make(), lambda cid: False).allowed


def test_policy_rejects_unknown_table():
    decision = check_eligibility(make(tables=["customers", "invoices"]), lambda cid: False)
    assert not decision.allowed
    assert "invoices" in decision.reason
