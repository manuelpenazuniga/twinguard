"""Text helpers for the review log: quantities, percentages and one-line summaries.

{{UNRELATED_NOTE}}
"""


def format_quantity(value):
    sign = "-" if value < 0 else ""
    return f"{sign}{abs(int(value)):,}"


def format_percent(ratio, digits=1):
    return f"{ratio * 100:.{digits}f}%"


def summary_line(report):
    reasons = "; ".join(report.reasons) if report.reasons else "-"
    return (f"[{report.severity.value.upper()}] {report.order_id} {report.account}/"
            f"{report.symbol} pos={format_quantity(report.projected_position)} "
            f"limit={format_quantity(report.limit)} ({format_percent(report.utilisation())}) "
            f"{reasons}")
