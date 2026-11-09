"""Reference: issuing a card refund with the gateway v2 refunds API.

Adapted from the gateway SDK migration guide. v2 differences from v1:

* ``refunds_create`` replaces ``refund``; all arguments are keyword-only.
* Amounts are integer minor units plus an explicit ISO currency code.
* ``idempotency_key`` is mandatory; use the request id so retries never double-refund.
* The response carries ``refund_id`` and ``status`` (``succeeded``, ``pending`` or
  ``failed``). A ``pending`` refund has been accepted and settles asynchronously.
"""
from refunds.amounts import to_minor_units
from refunds.models import RefundResult


def issue_refund(gateway, request):
    amount_minor = to_minor_units(request.amount, request.currency)
    response = gateway.refunds_create(
        charge_id=request.charge_id,
        amount_minor=amount_minor,
        currency=request.currency.upper(),
        idempotency_key=request.request_id,
        reason=request.reason,
    )
    status = response["status"]
    if status == "failed":
        return RefundResult(request.request_id, "declined",
                            detail=response.get("failure_reason", ""))
    return RefundResult(request.request_id, "issued", refund_id=response["refund_id"],
                        settled=status == "succeeded")
