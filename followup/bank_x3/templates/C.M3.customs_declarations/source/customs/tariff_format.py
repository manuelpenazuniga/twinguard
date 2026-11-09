"""{{UNRELATED_NOTE}}"""
from decimal import ROUND_HALF_UP, Decimal


def normalise_hs_code(code):
    """Return an HS code as ``CCHH.SS`` (chapter, heading, subheading)."""
    digits = "".join(ch for ch in str(code) if ch.isdigit())
    if len(digits) < 6:
        raise ValueError(f"HS code needs at least 6 digits: {code!r}")
    return f"{digits[:4]}.{digits[4:6]}"


def hs_chapter(code):
    """Two-digit chapter of an HS code."""
    return normalise_hs_code(code)[:2]


def format_customs_value(amount, currency="EUR"):
    """Format a declared value with two decimals and a thousands separator."""
    value = Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{value:,.2f} {currency.upper()}"


def format_weight(kilograms):
    """Format a weight in kilograms with one decimal."""
    return f"{float(kilograms):,.1f} kg"
