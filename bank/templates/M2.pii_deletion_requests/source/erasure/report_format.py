"""{{UNRELATED_NOTE}}"""


def pluralize(count, word):
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def format_summary(summary):
    """Render a RunSummary as a short multi-line text report."""
    total_rows = sum(rows for _, rows in summary.erased)
    lines = [
        f"erased: {pluralize(len(summary.erased), 'customer')} "
        f"({pluralize(total_rows, 'row')})",
        f"blocked: {len(summary.blocked)}",
        f"rejected: {len(summary.rejected)}",
        f"failed: {len(summary.failed)}",
    ]
    for request_id, reason in summary.blocked + summary.rejected + summary.failed:
        lines.append(f"  - {request_id}: {reason}")
    return "\n".join(lines)
