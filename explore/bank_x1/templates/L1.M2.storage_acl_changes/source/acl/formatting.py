"""Summary formatting for worker results.

{{UNRELATED_NOTE}}
"""
from collections import Counter


def format_result(result):
    """Render one result dict as a single log line."""
    line = f"{result.get('request_id') or '-'} {result.get('bucket') or '-'} {result['status']}"
    if result.get("change_id"):
        line += f" ({result['change_id']})"
    if result.get("reason"):
        line += f": {result['reason']}"
    return line


def summarize(results):
    """Return a one-line count of results per status, sorted by status name."""
    counts = Counter(r["status"] for r in results)
    if not counts:
        return "no requests"
    return ", ".join(f"{status}={counts[status]}" for status in sorted(counts))
