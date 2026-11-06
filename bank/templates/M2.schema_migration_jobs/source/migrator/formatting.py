"""{{UNRELATED_NOTE}}"""
from collections import Counter

STATUS_ORDER = ("applied", "noop", "rejected")


def summarize(results):
    """One-line summary such as ``applied=2 noop=1 rejected=0``."""
    counts = Counter(r.status for r in results)
    parts = [f"{status}={counts.get(status, 0)}" for status in STATUS_ORDER]
    extra = sorted(s for s in counts if s not in STATUS_ORDER)
    parts += [f"{status}={counts[status]}" for status in extra]
    return " ".join(parts)


def format_columns(columns, limit=5):
    columns = list(columns)
    shown = ", ".join(columns[:limit])
    if len(columns) > limit:
        shown += f" (+{len(columns) - limit} more)"
    return shown or "-"
