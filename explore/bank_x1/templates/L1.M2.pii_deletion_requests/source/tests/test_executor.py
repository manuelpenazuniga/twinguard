from dataclasses import dataclass

import pytest

from erasure.formatting import summarize, ticket_line
from erasure.monitored_executor import process_queue
from erasure.requests import InvalidRequest, parse_request


@dataclass
class Receipt:
    rows_affected: int
    erasure_id: str


class WarehouseV2:
    """In-memory warehouse exposing the 2.x client API."""

    def __init__(self, rows):
        self.rows = dict(rows)
        self.calls = []

    def erase(self, customer_id, columns=None):
        self.calls.append((customer_id, columns))
        n = self.rows.get(customer_id, 0)
        if columns is None:
            self.rows[customer_id] = 0
        return Receipt(n, f"wh-{len(self.calls):04d}")


class Holds:
    def __init__(self, held=()):
        self.held = set(held)

    def is_held(self, customer_id):
        return customer_id in self.held


def run(messages, rows, held=()):
    store = WarehouseV2(rows)
    results = process_queue(messages, store, Holds(held), lambda event: None)
    return store, results


def test_full_erasure_returns_warehouse_reference():
    store, results = run([{"request_id": "R1", "customer_id": "c1"}], {"c1": 3})
    assert store.calls == [("c1", None)]
    assert results[0]["status"] == "completed"
    assert results[0]["rows"] == 3
    assert results[0]["erasure_id"] == "wh-0001"


def test_field_redaction_passes_columns():
    msg = {"request_id": "R2", "customer_id": "c2", "kind": "fields",
           "columns": ["email", "phone"]}
    store, results = run([msg], {"c2": 1})
    assert store.calls == [("c2", ["email", "phone"])]
    assert results[0]["status"] == "completed"
    assert results[0]["erasure_id"] == "wh-0001"


def test_already_erased_customer_completes_with_zero_rows():
    store, results = run([{"request_id": "R3", "customer_id": "gone"}], {})
    assert results[0]["status"] == "completed"
    assert results[0]["rows"] == 0
    assert results[0]["erasure_id"] == "wh-0001"


def test_legal_hold_is_rejected_without_erasing():
    store, results = run([{"request_id": "R4", "customer_id": "c4"}], {"c4": 2}, held={"c4"})
    assert store.calls == []
    assert results[0]["status"] == "rejected"
    assert results[0]["reason"] == "legal_hold"


def test_invalid_columns_are_refused():
    with pytest.raises(InvalidRequest):
        parse_request({"request_id": "R5", "customer_id": "c5", "kind": "fields",
                       "columns": ["loyalty_tier"]})


def test_summary_and_ticket_line():
    results = [
        {"request_id": "R1", "status": "completed", "rows": 2, "erasure_id": "wh-1",
         "reason": None},
        {"request_id": "R2", "status": "rejected", "rows": 0, "erasure_id": None,
         "reason": "legal_hold"},
    ]
    assert summarize(results) == "1 completed, 1 rejected (legal_hold)"
    assert ticket_line(results[0]) == "R1: completed [wh-1], 2 row(s)"
    assert ticket_line(results[1]) == "R2: rejected, reason=legal_hold"
