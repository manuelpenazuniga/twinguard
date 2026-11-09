"""Text helpers for rollout summaries.

{{UNRELATED_NOTE}}
"""


def short_version(version):
    parts = str(version).split(".")
    return ".".join(parts[:2]) if len(parts) > 2 and parts[2] == "0" else str(version)


def plural(count, word):
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def summarize(kind, group, version, device_count):
    return f"{kind} {group} -> v{short_version(version)} ({plural(device_count, 'device')})"
