"""{{UNRELATED_NOTE}}"""


def format_duration(seconds):
    """Render a duration as ``1h 05m 09s``; negative or zero durations render as ``0s``."""
    total = int(max(0, seconds))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}h {minutes:02d}m {secs:02d}s"
    if minutes:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"


def stream_label(stream_id, max_len=24):
    """Short, stable label for a stream identifier."""
    label = str(stream_id).strip()
    if len(label) > max_len:
        label = label[: max_len - 1] + "~"
    return f"stream:{label}"
