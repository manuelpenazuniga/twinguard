"""Executes queued PII erasure requests against the customer warehouse.

Requests are processed in queue order. Customers under a legal hold are never
erased; their requests are rejected and routed to the legal team.
"""
from erasure import action_auditor
from erasure.requests import FIELDS, FULL, parse_request

COMPLETED = "completed"
REJECTED = "rejected"


def _result(request, status, rows, erasure_id=None, reason=None):
    return {
        "request_id": request.request_id,
        "customer_id": request.customer_id,
        "kind": request.kind,
        "status": status,
        "rows": rows,
        "erasure_id": erasure_id,
        "reason": reason,
    }


def erase_customer(store, audit_hook, request):
    """Erase every warehouse row that belongs to the customer."""
    rows = store.delete_customer(request.customer_id)
    action_auditor.record_erasure(audit_hook, request, rows)
    return _result(request, COMPLETED, rows)


def redact_fields(store, audit_hook, request):
    """Null out the requested PII columns for the customer."""
    rows = store.null_columns(request.customer_id, list(request.columns))
    action_auditor.record_erasure(audit_hook, request, rows)
    return _result(request, COMPLETED, rows)


def execute_request(request, store, holds, audit_hook):
    """Run a single parsed request and return its result record."""
    if holds.is_held(request.customer_id):
        return _result(request, REJECTED, 0, reason="legal_hold")
    if request.kind == FULL:
        return erase_customer(store, audit_hook, request)
    if request.kind == FIELDS:
        return redact_fields(store, audit_hook, request)
    return _result(request, REJECTED, 0, reason="unsupported_kind")


def process_queue(messages, store, holds, audit_hook):
    """Process a batch of queue messages and return one result per message.

    `store` is the warehouse client, `holds` the legal-hold service and
    `audit_hook` the privacy audit hook callable.
    """
    results = []
    for raw in messages:
        request = parse_request(raw)
        results.append(execute_request(request, store, holds, audit_hook))
    return results
