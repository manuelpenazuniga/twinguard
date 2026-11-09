"""Currency amount helpers: conversion to minor units and display formatting.

{{UNRELATED_NOTE}}
"""
from decimal import ROUND_HALF_UP, Decimal

MINOR_DIGITS = {"EUR": 2, "USD": 2, "GBP": 2, "CHF": 2, "JPY": 0, "KWD": 3}


def minor_digits(currency):
    try:
        return MINOR_DIGITS[currency.upper()]
    except KeyError:
        raise ValueError(f"unsupported currency {currency!r}") from None


def to_minor_units(amount, currency):
    """Convert a major-unit amount (Decimal, str or int) to integer minor units."""
    digits = minor_digits(currency)
    quantum = Decimal(1).scaleb(-digits)
    value = Decimal(str(amount)).quantize(quantum, rounding=ROUND_HALF_UP)
    return int(value.scaleb(digits))


def from_minor_units(minor, currency):
    return Decimal(int(minor)).scaleb(-minor_digits(currency))


def format_amount(minor, currency):
    """Render minor units for statements, e.g. ``1250, "EUR"`` -> ``"12.50 EUR"``."""
    digits = minor_digits(currency)
    value = from_minor_units(minor, currency)
    return f"{value:,.{digits}f} {currency.upper()}"
