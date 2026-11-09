from decimal import Decimal

import pytest

from refunds.amounts import format_amount, to_minor_units
from refunds.models import ChargeInfo, RefundRequest
from refunds.policy import check_refund_policy

CHARGE = ChargeInfo("ch_1", 5000, 1000, "EUR")


@pytest.mark.parametrize("amount, currency, minor", [
    ("12.50", "EUR", 1250), ("0.005", "EUR", 1), ("1500", "JPY", 1500), ("1.2345", "KWD", 1235),
])
def test_to_minor_units(amount, currency, minor):
    assert to_minor_units(Decimal(amount), currency) == minor


def test_format_amount():
    assert format_amount(123456, "EUR") == "1,234.56 EUR"
    assert format_amount(1500, "jpy") == "1,500 JPY"


@pytest.mark.parametrize("amount, currency, reason", [
    ("40.00", "EUR", None),
    ("40.01", "EUR", "exceeds_captured_amount"),
    ("0", "EUR", "invalid_amount"),
    ("10.00", "USD", "currency_mismatch"),
])
def test_policy(amount, currency, reason):
    request = RefundRequest("rq", "ch_1", Decimal(amount), currency)
    assert check_refund_policy(request, CHARGE) == reason


def test_unknown_and_disputed_charges():
    request = RefundRequest("rq", "ch_1", Decimal("1.00"), "EUR")
    assert check_refund_policy(request, None) == "unknown_charge"
    disputed = ChargeInfo("ch_1", 5000, 0, "EUR", disputed=True)
    assert check_refund_policy(request, disputed) == "charge_under_dispute"
