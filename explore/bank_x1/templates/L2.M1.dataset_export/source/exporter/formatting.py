"""{{UNRELATED_NOTE}}"""
from .models import Decision


def human_rows(count):
    for unit, size in (("B", 1_000_000_000), ("M", 1_000_000), ("k", 1_000)):
        if count >= size:
            return f"{count / size:.1f}{unit}"
    return str(count)


class RunSummaryFormatter:
    """Turns a RunReport into a short plain-text block."""

    def __init__(self, width=60):
        self._width = width

    def headline(self, report):
        counts = {d: len(report.by_decision(d)) for d in Decision}
        failed = sum(1 for o in report.outcomes if o.error)
        return (f"run {report.run_id}: {counts[Decision.ALLOW]} exported, "
                f"{counts[Decision.DENY]} denied, {counts[Decision.HOLD]} held, "
                f"{failed} failed")

    def render(self, report, requests=()):
        rows = {r.request_id: r.row_count for r in requests}
        lines = [self.headline(report), "-" * self._width]
        for outcome in report.outcomes:
            size = human_rows(rows[outcome.request_id]) if outcome.request_id in rows else "?"
            status = "failed" if outcome.error else outcome.decision.value
            lines.append(f"{outcome.request_id:<24}{status:<10}{size:>8}")
        return "\n".join(lines)
