"""{{UNRELATED_NOTE}}"""


def mask_secret(text, keep=4):
    """Hide all but the first ``keep`` characters of a matched value."""
    text = text.strip()
    if len(text) <= keep:
        return "*" * len(text)
    return text[:keep] + "*" * min(len(text) - keep, 12)


def truncate(text, width=60):
    text = " ".join(text.split())
    if len(text) <= width:
        return text
    return text[: width - 3] + "..."


def digest_line(build_id, level, count):
    noun = "finding" if count == 1 else "findings"
    return f"{build_id:<12} {level.upper():<8} {count} {noun}"
