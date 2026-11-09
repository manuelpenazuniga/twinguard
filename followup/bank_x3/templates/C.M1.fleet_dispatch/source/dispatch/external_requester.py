"""Reads dispatch requests from the inbound request queue (ExternalRequester).

Queue messages are plain dicts. They are validated and normalised here; nothing
in this module decides whether a vehicle may actually leave the depot.
"""
from dispatch.models import ROUTE_CLASSES, DispatchRequest, InvalidRequest

REQUIRED_FIELDS = ("request_id", "vehicle_id", "route_id", "route_class", "depot")


def parse_message(message):
    """Turn one queue message into a ``DispatchRequest``."""
    missing = [name for name in REQUIRED_FIELDS if not message.get(name)]
    if missing:
        raise InvalidRequest(f"message missing fields: {', '.join(missing)}")
    route_class = str(message["route_class"]).strip().lower()
    if route_class not in ROUTE_CLASSES:
        raise InvalidRequest(f"unknown route class {message['route_class']!r}")
    return DispatchRequest(
        request_id=str(message["request_id"]).strip(),
        vehicle_id=str(message["vehicle_id"]).strip().upper(),
        route_id=str(message["route_id"]).strip().upper(),
        route_class=route_class,
        depot=str(message["depot"]).strip().upper(),
        pickup_window=str(message.get("pickup_window", "next-shift")),
        tags=tuple(sorted(set(message.get("tags", ())))),
    )


def read_requests(messages):
    """Yield ``(request_id, request_or_error)`` pairs in queue order.

    Malformed messages are reported with the ``InvalidRequest`` instance in
    place of a request so the caller can record them without stopping.
    """
    seen = set()
    for index, message in enumerate(messages):
        key = message.get("request_id") or f"#{index}"
        try:
            request = parse_message(message)
        except InvalidRequest as exc:
            yield key, exc
            continue
        if request.request_id in seen:
            yield key, InvalidRequest(f"duplicate request id {request.request_id}")
            continue
        seen.add(request.request_id)
        yield request.request_id, request
