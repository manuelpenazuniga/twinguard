"""Safe operating envelope for plant control tags.

An envelope maps a control tag (for example ``boiler-2.temp``) to the lowest and
highest setpoint the process engineers have signed off, plus a warning margin
expressed as a fraction of the allowed span.
"""

IN_RANGE = "in_range"
NEAR_LIMIT = "near_limit"
OUT_OF_RANGE = "out_of_range"
UNKNOWN_TAG = "unknown_tag"

DEFAULT_MARGIN = 0.05


def make_limits(low, high, unit, margin=DEFAULT_MARGIN):
    if low >= high:
        raise ValueError(f"invalid limits: low={low} high={high}")
    return {"low": float(low), "high": float(high), "unit": unit, "margin": float(margin)}


def load_envelope(rows):
    """Build an envelope from ``(tag, low, high, unit)`` rows."""
    return {tag: make_limits(low, high, unit) for tag, low, high, unit in rows}


def classify(envelope, tag, value):
    """Return ``(status, limits)`` for a proposed setpoint value."""
    limits = envelope.get(tag)
    if limits is None:
        return UNKNOWN_TAG, None
    low, high = limits["low"], limits["high"]
    if value < low or value > high:
        return OUT_OF_RANGE, limits
    band = (high - low) * limits["margin"]
    if value < low + band or value > high - band:
        return NEAR_LIMIT, limits
    return IN_RANGE, limits


def nearest_limit(limits, value):
    if limits is None:
        return None
    if abs(value - limits["low"]) <= abs(value - limits["high"]):
        return limits["low"]
    return limits["high"]
