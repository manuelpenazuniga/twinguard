"""Plain-text rendering of deploy run outcomes.

{{UNRELATED_NOTE}}
"""
from collections import Counter


def summarize(outcomes) -> str:
    counts = Counter(o.status for o in outcomes.values())
    parts = [f"{status}={counts[status]}" for status in sorted(counts)]
    return f"{len(outcomes)} request(s): " + (", ".join(parts) if parts else "none")


def render_table(outcomes) -> str:
    rows = [("REQUEST", "STATUS", "DETAIL")]
    rows += [(o.request_id, o.status, o.detail) for o in outcomes.values()]
    widths = [max(len(r[i]) for r in rows) for i in range(3)]
    return "\n".join("  ".join(c.ljust(w) for c, w in zip(r, widths)).rstrip() for r in rows)
