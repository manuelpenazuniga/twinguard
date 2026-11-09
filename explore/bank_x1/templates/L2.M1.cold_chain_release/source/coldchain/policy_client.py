"""Thin client for the cold-chain policy service.

The service transport is injected as ``evaluate(payload, timeout)``; it returns
a mapping with a ``decision`` key and raises ``TimeoutError`` when the service
does not answer in time.
"""
from coldchain.models import Decision, PolicyTimeout

DEFAULT_TIMEOUT_S = 2.0

_DECISIONS = {d.value: d for d in Decision}


def build_payload(request):
    """Serialise a release request into the policy service schema."""
    return {
        "request_id": request.request_id,
        "pallet_id": request.pallet_id,
        "sku": request.sku,
        "dock_door": request.dock_door,
        "temperature_c": request.temperature_c,
        "range_c": [request.min_c, request.max_c],
    }


def parse_decision(response):
    """Map a service response onto a Decision; unknown values are rejected."""
    value = str(response.get("decision", "")).strip().lower()
    if value not in _DECISIONS:
        raise ValueError(f"unexpected policy decision {value!r}")
    return _DECISIONS[value]


def fetch_decision(evaluate, request, timeout_s=DEFAULT_TIMEOUT_S):
    """Ask the policy service for a decision on one request."""
    try:
        response = evaluate(build_payload(request), timeout=timeout_s)
    except TimeoutError as exc:
        raise PolicyTimeout(request.pallet_id, timeout_s) from exc
    return parse_decision(response)
