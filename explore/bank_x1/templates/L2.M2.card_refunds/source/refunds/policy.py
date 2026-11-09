"""Refund eligibility rules applied before any money moves."""
from .amounts import to_minor_units


def check_refund_policy(request, charge):
    """Return a rejection reason for ``request`` against ``charge``, or None if allowed."""
    if charge is None:
        return "unknown_charge"
    if request.currency.upper() != charge.currency.upper():
        return "currency_mismatch"
    try:
        amount_minor = to_minor_units(request.amount, request.currency)
    except (ValueError, ArithmeticError):
        return "invalid_amount"
    if amount_minor <= 0:
        return "invalid_amount"
    if charge.disputed:
        return "charge_under_dispute"
    if charge.refunded_minor + amount_minor > charge.captured_minor:
        return "exceeds_captured_amount"
    return None
