"""{{UNRELATED_NOTE}}"""

from collections.abc import Iterable


def rx_label(drug: str, strength: str, quantity: int) -> str:
    """Return a compact label such as ``Lisinopril 10 mg x30``."""
    return f"{drug.strip().title()} {strength.strip()} x{quantity}"


def pluralize(count: int, singular: str, plural: str | None = None) -> str:
    word = singular if count == 1 else (plural or singular + "s")
    return f"{count} {word}"


def summary_line(results: Iterable[dict]) -> str:
    """One-line summary of a drained queue, e.g. ``3 renewals: 2 issued, 1 held``."""
    results = list(results)
    issued = sum(1 for r in results if r.get("status") == "issued")
    held = sum(1 for r in results if r.get("status") == "held")
    return f"{pluralize(len(results), 'renewal')}: {issued} issued, {held} held"
