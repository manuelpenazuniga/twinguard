"""Client for the permit policy service.

The service is reached through a ``transport`` callable so that the worker can
run against the HTTP gateway in production and against fakes in tests.
"""
from dispatch.models import PermitServiceTimeout

DEFAULT_TIMEOUT_S = 2.0


def build_payload(request):
    return {
        "route_id": request.route_id,
        "route_class": request.route_class,
        "vehicle_id": request.vehicle_id,
        "depot": request.depot,
        "pickup_window": request.pickup_window,
    }


def make_permit_lookup(transport, timeout_s=DEFAULT_TIMEOUT_S):
    """Return ``lookup(request) -> verdict`` backed by ``transport``.

    ``transport(payload, timeout_s)`` returns a dict with a ``verdict`` key and
    raises ``TimeoutError`` when the service does not answer in time.
    """

    def lookup(request):
        try:
            reply = transport(build_payload(request), timeout_s)
        except TimeoutError as exc:
            raise PermitServiceTimeout(request.request_id, timeout_s) from exc
        return reply.get("verdict", "pending_review")

    return lookup
