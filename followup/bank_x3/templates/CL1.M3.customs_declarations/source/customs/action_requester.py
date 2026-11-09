"""Intake of customs declarations from the broker request queue.

Each queued request is validated, normalised and filed with the registry. Filing publishes
a ``declaration.filed`` event that the screening handlers subscribe to.
"""
from .tariff_format import normalise_hs_code

SUBMITTED = "declaration.submitted"
FILED_EVENT = "declaration.filed"
REQUIRED_FIELDS = ("declaration_id", "hs_code", "description", "gross_weight_kg",
                   "manifest_weight_kg", "declared_hazardous")


class DeclarationRejected(ValueError):
    """The request cannot be filed as a declaration."""


def normalise_declaration(request):
    missing = [name for name in REQUIRED_FIELDS if name not in request]
    if missing:
        raise DeclarationRejected(f"{request.get('declaration_id', '?')}: missing {missing}")
    declaration = dict(request)
    declaration["hs_code"] = normalise_hs_code(request["hs_code"])
    declaration["gross_weight_kg"] = float(request["gross_weight_kg"])
    declaration["manifest_weight_kg"] = float(request["manifest_weight_kg"])
    declaration["declared_hazardous"] = bool(request["declared_hazardous"])
    declaration["un_number"] = (request.get("un_number") or "").strip().upper() or None
    return declaration


def file_declaration(bus, registry, request):
    """File one declaration and announce it on the bus."""
    declaration = normalise_declaration(request)
    registry.file(declaration)
    bus.publish(FILED_EVENT, {"declaration": declaration})
    return declaration


def register_action_requester(bus, registry):
    """Subscribe the filing handler to submitted requests."""

    def on_declaration_submitted(event):
        file_declaration(bus, registry, event["request"])

    bus.subscribe(SUBMITTED, on_declaration_submitted)
    return on_declaration_submitted


def drain_request_queue(bus, queue):
    """Submit every pending request in ``queue`` (a deque); returns the number processed."""
    processed = 0
    while queue:
        request = queue.popleft()
        bus.publish(SUBMITTED, {"request": request})
        processed += 1
    return processed
