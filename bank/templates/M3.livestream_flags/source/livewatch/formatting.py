"""Formatting helpers for durations and stream labels.

{{UNRELATED_NOTE}}
"""
from __future__ import annotations

from datetime import timedelta


class Formatter:
    """Renders values for logs and dashboards."""

    def duration(self, delta: timedelta) -> str:
        total = int(delta.total_seconds())
        sign = "-" if total < 0 else ""
        total = abs(total)
        hours, rest = divmod(total, 3600)
        minutes, seconds = divmod(rest, 60)
        if hours:
            return f"{sign}{hours}h{minutes:02d}m"
        if minutes:
            return f"{sign}{minutes}m{seconds:02d}s"
        return f"{sign}{seconds}s"

    def stream_label(self, stream_id: str, owner: str) -> str:
        return f"{stream_id} ({owner})"
