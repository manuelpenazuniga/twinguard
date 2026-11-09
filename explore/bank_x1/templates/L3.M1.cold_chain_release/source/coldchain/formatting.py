"""{{UNRELATED_NOTE}}"""


def format_temperature(value_c):
    """Render a Celsius reading with one decimal and an explicit sign."""
    return f"{value_c:+.1f}°C"


def format_reading(request):
    """One-line description of a pallet's last logger reading."""
    return (f"{request.sku} at {format_temperature(request.temperature_c)} "
            f"(range {format_temperature(request.min_c)}..{format_temperature(request.max_c)})")


def format_summary(summary):
    """Compact counts for a run summary, in a stable order."""
    return ", ".join(f"{key}={len(summary.get(key, []))}"
                     for key in ("released", "held", "denied"))
