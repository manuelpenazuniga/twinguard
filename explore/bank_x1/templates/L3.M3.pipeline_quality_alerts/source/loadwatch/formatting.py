"""Number and percentage formatting.

{{UNRELATED_NOTE}}
"""


def format_count(n):
    """1234567 -> '1,234,567'."""
    return f"{int(n):,}"


def format_ratio(part, total, digits=1):
    """Percentage of ``part`` in ``total``; '0.0%' when ``total`` is zero."""
    if not total:
        return f"{0:.{digits}f}%"
    return f"{100.0 * part / total:.{digits}f}%"
