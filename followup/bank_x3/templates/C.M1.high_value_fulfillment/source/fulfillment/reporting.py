"""{{UNRELATED_NOTE}}"""

CURRENCY_SYMBOLS = {"USD": "$", "EUR": "€", "GBP": "£"}


def format_amount(amount_cents, currency):
    """Render an amount in minor units, e.g. ``format_amount(123456, "USD")``."""
    symbol = CURRENCY_SYMBOLS.get(currency.upper())
    whole, cents = divmod(abs(int(amount_cents)), 100)
    sign = "-" if amount_cents < 0 else ""
    if symbol:
        return f"{sign}{symbol}{whole:,}.{cents:02d}"
    return f"{sign}{whole:,}.{cents:02d} {currency.upper()}"


def format_summary(summary):
    """One-line run summary for the job log."""
    return (
        f"release run: {summary['processed']} processed, "
        f"{summary['released']} released, {summary['held']} held, "
        f"{summary['denied']} denied"
    )
