"""{{UNRELATED_NOTE}}

Lines are plain ASCII and never longer than ``MAX_WIDTH`` characters.
"""

MAX_WIDTH = 100


def short_digest(digest, length=12):
    """Return ``sha256:abcdef123456`` style abbreviations of a digest."""
    if not digest:
        return "-"
    algo, _, value = digest.partition(":")
    if not value:
        return digest[:length]
    return f"{algo}:{value[:length]}"


def format_outcome(outcome):
    status = outcome.get("status", "unknown")
    request_id = outcome.get("request_id") or "?"
    if status == "rejected":
        line = f"[{request_id}] rejected: {outcome.get('reason', '')}"
    else:
        suffix = "" if outcome.get("changed", True) else " (unchanged)"
        line = f"[{request_id}] {status} {outcome.get('artifact')} {short_digest(outcome.get('digest'))}{suffix}"
    if len(line) > MAX_WIDTH:
        line = line[: MAX_WIDTH - 3] + "..."
    return line


def format_summary(outcomes):
    counts = {}
    for outcome in outcomes:
        counts[outcome.get("status", "unknown")] = counts.get(outcome.get("status", "unknown"), 0) + 1
    totals = ", ".join(f"{k}={counts[k]}" for k in sorted(counts)) or "no requests"
    return "\n".join([format_outcome(o) for o in outcomes] + [f"total: {totals}"])
