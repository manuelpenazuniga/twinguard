"""{{UNRELATED_NOTE}}

Amounts are kept in minor units (cents) everywhere in the desk; these helpers
only exist for operator-facing output.
"""

_EXPONENTS = {"JPY": 0, "KWD": 3, "BHD": 3}


def format_amount(amount_minor, currency):
    exponent = _EXPONENTS.get(currency, 2)
    if exponent == 0:
        return f"{amount_minor:,} {currency}"
    sign = "-" if amount_minor < 0 else ""
    major, minor = divmod(abs(amount_minor), 10 ** exponent)
    return f"{sign}{major:,}.{minor:0{exponent}d} {currency}"


def mask_account(account):
    digits = account.replace(" ", "")
    if len(digits) <= 4:
        return digits
    return "*" * (len(digits) - 4) + digits[-4:]


def summary_line(summary):
    return (f"sent={len(summary.sent)} held={len(summary.held)} "
            f"rejected={len(summary.rejected)}")
