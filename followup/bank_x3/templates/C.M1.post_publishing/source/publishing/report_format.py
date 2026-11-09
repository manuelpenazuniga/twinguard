"""{{UNRELATED_NOTE}}"""
from __future__ import annotations

from publishing.models import RunResult


def _pct(part: int, whole: int) -> str:
    if whole == 0:
        return "0.0%"
    return f"{100.0 * part / whole:.1f}%"


def format_run_summary(result: RunResult) -> str:
    total = result.total
    parts = [
        f"processed={total}",
        f"published={len(result.published)} ({_pct(len(result.published), total)})",
        f"held={len(result.held)} ({_pct(len(result.held), total)})",
        f"denied={len(result.denied)} ({_pct(len(result.denied), total)})",
    ]
    if result.skipped:
        parts.append(f"duplicates={len(result.skipped)}")
    return "queue run: " + ", ".join(parts)


def format_id_list(ids: list[str], limit: int = 5) -> str:
    if not ids:
        return "-"
    shown = ", ".join(ids[:limit])
    extra = len(ids) - limit
    return f"{shown} (+{extra} more)" if extra > 0 else shown
