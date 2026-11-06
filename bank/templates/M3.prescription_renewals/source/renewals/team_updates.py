"""Optional status summaries posted to the team channel after a queue run."""

from collections.abc import Callable, Iterable

from renewals.formatting import summary_line


def post_queue_summary(results: Iterable[dict], post: Callable[[str], None],
                       enabled: bool = True) -> str | None:
    """Post a one-line summary of the run; returns the text, or None when disabled."""
    if not enabled:
        return None
    text = summary_line(results)
    post(text)
    return text
