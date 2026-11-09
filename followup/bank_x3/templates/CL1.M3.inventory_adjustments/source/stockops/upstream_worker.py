"""Upstream worker handlers: apply stock adjustment requests from the request queue.

Each request taken from the queue is validated, posted to the ledger and then
published as an ``adjustment.reported`` event for the downstream handlers.
Requests that cannot be applied are published too, with status ``rejected``.
"""

REQUESTED = "adjustment.requested"
REPORTED = "adjustment.reported"

# Sign applied to the requested quantity for each adjustment kind.
KINDS = {
    "write_off": -1,
    "recount_gain": 1,
    "recount_loss": -1,
    "return_to_stock": 1,
}


def validate_request(request, ledger):
    """Return a rejection reason, or None when the request can be applied."""
    item = ledger.get(request.get("sku"))
    if item is None:
        return "unknown_sku"
    if request.get("kind") not in KINDS:
        return "unknown_kind"
    quantity = request.get("quantity")
    if not isinstance(quantity, int) or quantity <= 0:
        return "invalid_quantity"
    if KINDS[request["kind"]] < 0 and quantity > item.on_hand:
        return "insufficient_stock"
    return None


def apply_adjustment(request, ledger):
    """Post the adjustment to the ledger; return (signed delta, value at cost)."""
    item = ledger.get(request["sku"])
    delta = KINDS[request["kind"]] * request["quantity"]
    ledger.post(item.sku, delta, request["request_id"])
    return delta, round(request["quantity"] * item.unit_cost, 2)


def build_report(request, status, delta=0, value=None, reason=None):
    return {
        "request_id": request.get("request_id"),
        "sku": request.get("sku"),
        "kind": request.get("kind"),
        "quantity": request.get("quantity"),
        "submitted_by": request.get("submitted_by"),
        "delta": delta,
        "value": value,
        "status": status,
        "reason": reason,
    }


def register_upstream_worker(bus, ledger):
    """Subscribe the worker handler to queued adjustment requests."""

    def on_adjustment_requested(request):
        reason = validate_request(request, ledger)
        if reason is not None:
            bus.publish(REPORTED, build_report(request, "rejected", reason=reason))
            return None
        delta, value = apply_adjustment(request, ledger)
        report = build_report(request, "applied", delta, value)
        bus.publish(REPORTED, report)
        return report

    bus.subscribe(REQUESTED, on_adjustment_requested)
    return on_adjustment_requested
