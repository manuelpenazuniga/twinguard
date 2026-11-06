"""Text helpers for the end-of-shift release report.

{{UNRELATED_NOTE}}
"""


def format_temp(value_c: float) -> str:
    return f"{value_c:+.1f} °C"


def format_summary(counts: dict) -> str:
    parts = [f"{key}={counts.get(key, 0)}" for key in ("release", "hold", "deny")]
    return f"{counts.get('total', 0)} requests: " + ", ".join(parts)
