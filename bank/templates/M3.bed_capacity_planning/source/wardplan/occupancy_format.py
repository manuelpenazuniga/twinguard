"""Text formatting helpers for occupancy figures.

{{UNRELATED_NOTE}}
"""


def percent(part, whole):
    """Format a ratio as a whole-number percentage; empty totals give 0%."""
    if not whole:
        return "0%"
    return f"{round(100 * part / whole)}%"


def ward_label(ward):
    """Short display label such as ``4W (medical)``."""
    return f"{ward['ward_id']} ({ward['unit_type'].replace('_', ' ')})"


def occupancy_line(ward, capacity):
    """One summary line for a ward: label, occupied/capacity and percentage."""
    occupied = len(ward["patients"])
    return f"{ward_label(ward)}: {occupied}/{capacity} staffed beds, {percent(occupied, capacity)}"


def pluralise(count, noun):
    """``1 assignment`` / ``3 assignments``."""
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"
