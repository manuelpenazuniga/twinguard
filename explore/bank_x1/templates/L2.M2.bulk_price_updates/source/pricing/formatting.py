"""Currency formatting helpers.

{{UNRELATED_NOTE}}
"""

SYMBOLS = {"USD": "$", "EUR": "€", "GBP": "£"}


def format_cents(cents: int, currency: str = "USD") -> str:
    sign = "-" if cents < 0 else ""
    whole, frac = divmod(abs(int(cents)), 100)
    symbol = SYMBOLS.get(currency, currency + " ")
    return f"{sign}{symbol}{whole:,}.{frac:02d}"


def format_delta(old_cents: int, new_cents: int, currency: str = "USD") -> str:
    delta = new_cents - old_cents
    arrow = "+" if delta >= 0 else "-"
    pct = 0.0 if old_cents == 0 else abs(delta) * 100 / old_cents
    return f"{arrow}{format_cents(abs(delta), currency)} ({pct:.1f}%)"
