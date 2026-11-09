"""Text helpers that turn a broadcast job into the notice customers receive.

{{UNRELATED_NOTE}}
"""

MAX_BODY_CHARS = 480
ELLIPSIS = "..."

SEVERITY_PREFIX = {
    "maintenance": "[Planned maintenance]",
    "incident": "[Service incident]",
    "resolved": "[Resolved]",
}


def truncate_body(body, limit=MAX_BODY_CHARS):
    """Cut ``body`` to ``limit`` characters on a word boundary when possible."""
    text = " ".join(body.split())
    if len(text) <= limit:
        return text
    cut = text[: limit - len(ELLIPSIS)]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut + ELLIPSIS


def subject_line(kind, title):
    prefix = SEVERITY_PREFIX.get(kind, "[Notice]")
    return f"{prefix} {title.strip()}"


def render_notice(job):
    """Return the ``(subject, body)`` pair sent to the audience of ``job``."""
    return subject_line(job.kind, job.title), truncate_body(job.body)
