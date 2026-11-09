"""Formatting helpers for the end-of-shift dispatch summary.

{{UNRELATED_NOTE}}
"""
from collections import Counter

OUTCOME_ORDER = ("dispatched", "held", "denied", "rejected")


def count_outcomes(outcomes):
    counts = Counter(outcomes.values())
    return {name: counts.get(name, 0) for name in OUTCOME_ORDER}


def format_summary(outcomes, depot=None):
    """One-line summary such as ``DEP-N: 3 dispatched, 1 held, 0 denied, 0 rejected``."""
    counts = count_outcomes(outcomes)
    body = ", ".join(f"{counts[name]} {name}" for name in OUTCOME_ORDER)
    return f"{depot}: {body}" if depot else body


def format_table(outcomes):
    """Fixed-width table of request ids and outcomes, sorted by request id."""
    if not outcomes:
        return "(no requests)"
    width = max(len(str(k)) for k in outcomes)
    return "\n".join(f"{str(k).ljust(width)}  {v}" for k, v in sorted(outcomes.items()))
