"""Plain-text formatting helpers for restock run summaries.

{{UNRELATED_NOTE}}
"""
from .models import Outcome, RunReport

_ORDER = (Outcome.LOADED, Outcome.HELD, Outcome.DENIED, Outcome.REJECTED)


class SummaryFormatter:
    def __init__(self, width: int = 32):
        self._width = width

    def headline(self, report: RunReport) -> str:
        parts = [f"{report.count(o)} {o.value}" for o in _ORDER if report.count(o)]
        return ", ".join(parts) if parts else "no orders"

    def table(self, report: RunReport) -> str:
        rows = [f"{'order':<{self._width}}outcome"]
        for r in report.results:
            rows.append(f"{r.order_id:<{self._width}}{r.outcome.value}")
        return "\n".join(rows)

    def render(self, report: RunReport) -> str:
        return f"Restock run: {self.headline(report)}\n{self.table(report)}"
