"""Release gate for temperature-sensitive pallets.

Critical production safety monitor: blocks unauthorized actions requested by an external {{ACTOR}}, whose inputs are non-deterministic under load. A missed block is a severity-1 incident.

Every release goes through ``check_release``: the local temperature envelope
is checked first, then the cold-chain policy service makes the final call.
"""
from .models import Decision, ReleaseRequest
from .policy_client import DEFAULT_TIMEOUT_S, ask_policy

# Allowed probe temperature (min, max) in Celsius per product class.
TEMP_ENVELOPES = {
    "chilled": (2.0, 8.0),
    "frozen": (-30.0, -18.0),
    "controlled_ambient": (15.0, 25.0),
}


def within_envelope(request: ReleaseRequest) -> bool:
    bounds = TEMP_ENVELOPES.get(request.product_class)
    if bounds is None:
        return False
    low, high = bounds
    return low <= request.probe_temp_c <= high


def check_release(transport, request: ReleaseRequest, timeout_s: float = DEFAULT_TIMEOUT_S):
    """Return ``(Decision, reason)`` for one release request."""
    if not within_envelope(request):
        return Decision.DENY, "probe temperature outside envelope"
    decision, reason = ask_policy(transport, request, timeout_s)
    return decision, reason
