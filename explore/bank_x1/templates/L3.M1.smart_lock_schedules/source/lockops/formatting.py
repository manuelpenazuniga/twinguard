"""{{UNRELATED_NOTE}}"""
from __future__ import annotations

from typing import Iterable

from .models import UnlockWindow

DAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def format_minute(minute: int) -> str:
    hours, mins = divmod(minute, 60)
    return f"{hours:02d}:{mins:02d}"


def describe_window(window: UnlockWindow) -> str:
    return (
        f"{DAY_NAMES[window.day]} "
        f"{format_minute(window.start_minute)}-{format_minute(window.end_minute)}"
    )


def describe_windows(windows: Iterable[UnlockWindow]) -> str:
    ordered = sorted(windows, key=lambda w: (w.day, w.start_minute))
    if not ordered:
        return "always locked"
    return ", ".join(describe_window(w) for w in ordered)


def weekly_unlocked_hours(windows: Iterable[UnlockWindow]) -> float:
    return round(sum(w.duration for w in windows) / 60, 2)
