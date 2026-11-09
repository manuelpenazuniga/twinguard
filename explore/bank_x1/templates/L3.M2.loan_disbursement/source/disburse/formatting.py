"""Currency formatting helpers for ledger memos and operator reports.

{{UNRELATED_NOTE}}
"""


def format_cents(amount_cents, currency="EUR"):
    """Render an integer amount of cents as ``EUR 1,234.56``."""
    sign = "-" if amount_cents < 0 else ""
    units, cents = divmod(abs(amount_cents), 100)
    return f"{sign}{currency} {units:,}.{cents:02d}"


def tranche_memo(loan_id, tranche_no, amount_cents):
    """Memo line shown on the borrower's statement."""
    return f"{loan_id} T{tranche_no:02d} {format_cents(amount_cents)}"
