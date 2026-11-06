"""Drains the deletion request queue and performs customer-record erasures."""
from dataclasses import dataclass, field

from erasure.action_auditor import audit_erasure
from erasure.policy import check_eligibility
from erasure.requests import parse_request


@dataclass
class RunSummary:
    erased: list = field(default_factory=list)    # (customer_id, rows_erased)
    blocked: list = field(default_factory=list)   # (request_id, reason)
    rejected: list = field(default_factory=list)  # (request_id, reason)
    failed: list = field(default_factory=list)    # (request_id, error)


def erase_customer_record(store, request, audit_hook):
    """Erase one customer's records in the record store; return rows removed."""
    removed = []

    def _on_complete(rows_deleted):
        removed.append(rows_deleted)
        audit_erasure(audit_hook, request, rows_deleted)

    store.delete_customer(
        request.customer_id,
        tables=list(request.tables),
        on_complete=_on_complete,
    )
    return sum(removed)


def process_queue(messages, *, store, audit_hook, is_on_hold):
    """Process a batch of queue messages and return a RunSummary."""
    summary = RunSummary()
    for message in messages:
        try:
            request = parse_request(message)
        except ValueError as exc:
            summary.rejected.append((str(message.get("request_id", "?")), str(exc)))
            continue
        decision = check_eligibility(request, is_on_hold)
        if not decision.allowed:
            summary.blocked.append((request.request_id, decision.reason))
            continue
        try:
            rows = erase_customer_record(store, request, audit_hook)
        except Exception as exc:  # one bad request must not stall the queue
            summary.failed.append((request.request_id, f"{type(exc).__name__}: {exc}"))
            continue
        summary.erased.append((request.customer_id, rows))
    return summary
