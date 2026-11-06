"""Thin client for the cold-chain policy service.

The transport is injected: it is a callable ``transport(payload, timeout_s)``
that returns the decoded JSON reply as a dict and raises ``TimeoutError`` when
the service does not answer within ``timeout_s``.
"""
from .models import Decision, ReleaseRequest

DEFAULT_TIMEOUT_S = 2.0

_VERDICTS = {
    "allow": Decision.RELEASE,
    "hold": Decision.HOLD,
    "deny": Decision.DENY,
}


def build_payload(request: ReleaseRequest) -> dict:
    return {
        "request_id": request.request_id,
        "pallet_id": request.pallet_id,
        "product_class": request.product_class,
        "dock": request.dock,
        "probe_temp_c": round(request.probe_temp_c, 1),
    }


def ask_policy(transport, request: ReleaseRequest, timeout_s: float = DEFAULT_TIMEOUT_S):
    """Return ``(Decision, reason)`` as decided by the policy service."""
    reply = transport(build_payload(request), timeout_s)
    verdict = str(reply.get("verdict", "")).lower()
    if verdict not in _VERDICTS:
        raise ValueError(f"unexpected policy verdict {verdict!r} for {request.request_id}")
    return _VERDICTS[verdict], str(reply.get("reason", ""))
