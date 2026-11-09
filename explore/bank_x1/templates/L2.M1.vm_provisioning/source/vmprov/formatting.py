"""Text formatting for provisioning run reports.

{{UNRELATED_NOTE}}
"""
from __future__ import annotations

from .models import RunSummary


def plural(count: int, word: str) -> str:
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def format_id_list(ids: list[str], limit: int = 5) -> str:
    if not ids:
        return "-"
    shown = ", ".join(ids[:limit])
    extra = len(ids) - limit
    return f"{shown} (+{extra} more)" if extra > 0 else shown


def format_summary(summary: RunSummary) -> str:
    instances = sum(len(v) for v in summary.instances.values())
    lines = [
        f"processed {plural(summary.processed, 'request')}, "
        f"created {plural(instances, 'instance')}",
        f"  provisioned: {format_id_list(summary.provisioned)}",
        f"  denied:      {format_id_list(summary.denied)}",
        f"  held:        {format_id_list(summary.held)}",
    ]
    return "\n".join(lines)
