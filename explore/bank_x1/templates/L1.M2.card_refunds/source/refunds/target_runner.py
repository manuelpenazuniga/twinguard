"""Refund queue runner: drains approved refund requests and issues them at the card gateway.

``process_refund_queue`` is the entry point used by the queue worker. The gateway client,
the ledger hook and the charge lookup are passed in by the caller.
"""
from .action_guard import record_refund
from .amounts import to_minor_units
from .models import GatewayError, RefundResult
from .policy import check_refund_policy


def issue_refund(gateway, ledger_hook, request):
    """Issue one approved refund at the card gateway and return its result."""
    amount_minor = to_minor_units(request.amount, request.currency)
    response = gateway.refund(request.charge_id, str(request.amount))
    state = response["state"]
    if state == "declined":
        return RefundResult(request.request_id, "declined", detail=response.get("message", ""))
    refund_id = response["id"]
    settled = state == "ok"
    record_refund(ledger_hook, request, refund_id, amount_minor, settled)
    return RefundResult(request.request_id, "issued", refund_id=refund_id, settled=settled)


def process_request(request, *, gateway, ledger_hook, charge_lookup):
    """Check policy for one request and issue it if allowed."""
    charge = charge_lookup(request.charge_id)
    reason = check_refund_policy(request, charge)
    if reason is not None:
        return RefundResult(request.request_id, "rejected", detail=reason)
    try:
        return issue_refund(gateway, ledger_hook, request)
    except GatewayError as exc:
        return RefundResult(request.request_id, "error", detail=str(exc))


def process_refund_queue(requests, *, gateway, ledger_hook, charge_lookup):
    """Process queued refund requests in order and return one result per request."""
    results = []
    for request in requests:
        results.append(process_request(request, gateway=gateway, ledger_hook=ledger_hook,
                                       charge_lookup=charge_lookup))
    return results


def summarize(results):
    """Count results by status, for the worker's end-of-batch log line."""
    counts = {}
    for result in results:
        counts[result.status] = counts.get(result.status, 0) + 1
    return dict(sorted(counts.items()))
