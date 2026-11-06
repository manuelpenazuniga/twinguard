"""Display helpers for temperatures and pipeline log lines.

{{UNRELATED_NOTE}}
"""

from __future__ import annotations

from setpoints.models import RunSummary, SetpointChange


def celsius(value: float) -> str:
    return f"{value:.1f} °C"


def fahrenheit(value_c: float) -> str:
    return f"{value_c * 9 / 5 + 32:.1f} °F"


def describe_change(change: SetpointChange) -> str:
    return f"{change.building}/{change.zone} -> {celsius(change.target_c)} ({change.mode})"


def summary_line(summary: RunSummary) -> str:
    return (
        f"processed={summary.processed} applied={len(summary.applied)} "
        f"held={len(summary.held)} denied={len(summary.denied)} "
        f"rejected={len(summary.rejected)}"
    )
