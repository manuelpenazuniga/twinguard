"""Formatting helpers.

{{UNRELATED_NOTE}}
"""


def format_money(amount, currency="EUR"):
    """Render an amount with thousands separators and two decimals."""
    return f"{currency} {amount:,.2f}"


def format_quantity(quantity, unit="unit"):
    """Render a quantity with a pluralised unit name."""
    label = unit if abs(quantity) == 1 else unit + "s"
    return f"{quantity:,} {label}"


def format_signed(delta):
    """Render a stock movement with an explicit sign."""
    return f"{delta:+,}"
