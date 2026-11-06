"""Display helpers for renewal summaries and pharmacy payloads.

{{UNRELATED_NOTE}}
"""


def mask_identifier(value, visible=4):
    value = str(value)
    if len(value) <= visible:
        return "*" * len(value)
    return "*" * (len(value) - visible) + value[-visible:]


def humanize_kind(kind):
    return kind.replace("_", " ").capitalize()


def review_summary(request_id, kind, medication):
    return f"{request_id}: {humanize_kind(kind)} ({medication})"
