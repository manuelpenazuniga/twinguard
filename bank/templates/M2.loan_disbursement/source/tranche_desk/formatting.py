"""{{UNRELATED_NOTE}}"""


def format_cents(amount_cents, currency="EUR"):
    sign = "-" if amount_cents < 0 else ""
    whole, cents = divmod(abs(int(amount_cents)), 100)
    return f"{sign}{whole:,}.{cents:02d} {currency}"


def tranche_reference(loan_id, tranche_id):
    return f"{loan_id}/T{int(tranche_id):03d}" if str(tranche_id).isdigit() \
        else f"{loan_id}/{tranche_id}"
