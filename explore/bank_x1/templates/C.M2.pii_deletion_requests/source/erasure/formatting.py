"""{{UNRELATED_NOTE}}"""
from collections import Counter


def summarize(results):
    """One-line summary such as '2 completed, 1 rejected (legal_hold)'."""
    if not results:
        return "no requests"
    statuses = Counter(r["status"] for r in results)
    parts = []
    for status in sorted(statuses):
        part = f"{statuses[status]} {status}"
        reasons = sorted({r["reason"] for r in results
                          if r["status"] == status and r.get("reason")})
        if reasons:
            part += f" ({', '.join(reasons)})"
        parts.append(part)
    return ", ".join(parts)


def ticket_line(result):
    """Line posted back to the privacy ticket for one request."""
    line = f"{result['request_id']}: {result['status']}"
    if result.get("erasure_id"):
        line += f" [{result['erasure_id']}]"
    if result["status"] == "completed":
        line += f", {result['rows']} row(s)"
    elif result.get("reason"):
        line += f", reason={result['reason']}"
    return line
