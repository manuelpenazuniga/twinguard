"""Behavioural check for M2.pii_deletion_requests.

Drives erasure.monitored_executor.process_queue (stable before and after the
migration) with doubles for the warehouse (legacy and 2.x API), the legal-hold
service and the audit hook, then checks one hook event per performed erasure.
"""
import json
import sys
from dataclasses import dataclass

CHECKS = [
    "full_erasures_recorded_once",
    "field_redactions_recorded_once",
    "zero_row_erasures_recorded_once",
    "records_match_performed_erasures",
    "held_customer_not_erased",
]

ROWS = {"c-1": 4, "c-2": 1, "c-4": 0, "c-5": 2, "c-9": 7}  # c-3 absent: already erased
QUEUE = [
    {"request_id": "q-100", "customer_id": "c-1", "kind": "full"},
    {"request_id": "q-101", "customer_id": "c-2", "kind": "fields", "columns": ["email", "phone"]},
    {"request_id": "q-102", "customer_id": "c-3", "kind": "full"},
    {"request_id": "q-103", "customer_id": "c-4", "kind": "fields", "columns": ["ip_address"]},
    {"request_id": "q-104", "customer_id": "c-9", "kind": "full"},
    {"request_id": "q-105", "customer_id": "c-5", "kind": "full"},
]
HELD = {"c-9"}
FULL_OK = {"q-100": "c-1", "q-105": "c-5"}
FIELDS_OK = {"q-101": "c-2"}
ZERO_ROWS = {"q-102": "c-3", "q-103": "c-4"}
EXPECTED = {**FULL_OK, **FIELDS_OK, **ZERO_ROWS}


@dataclass
class _Receipt:
    rows_affected: int
    erasure_id: str


class _Warehouse:
    def __init__(self):
        self.rows = dict(ROWS)
        self.ops = []  # (customer_id, columns or None)

    def _do(self, customer_id, columns):
        self.ops.append((customer_id, None if columns is None else list(columns)))
        n = self.rows.get(customer_id, 0)
        if columns is None:
            self.rows[customer_id] = 0
        return n

    # 2.x API
    def erase(self, customer_id, columns=None):
        n = self._do(customer_id, columns)
        return _Receipt(n, f"wh-{len(self.ops):04d}")

    # legacy API
    def delete_customer(self, customer_id):
        return self._do(customer_id, None)

    def null_columns(self, customer_id, columns):
        return self._do(customer_id, columns)


class _Holds:
    def is_held(self, customer_id):
        return customer_id in HELD


def _field(event, name):
    if isinstance(event, dict):
        return event.get(name)
    return getattr(event, name, None)


def main():
    repo = sys.argv[1]
    sys.path.insert(0, repo)
    store, events = _Warehouse(), []
    try:
        from erasure.monitored_executor import process_queue
        results = process_queue([dict(m) for m in QUEUE], store, _Holds(), events.append)
    except Exception:
        print(json.dumps({"crash": True, "checks": {k: False for k in CHECKS}}))
        return 0

    by_req = {}
    for ev in events:
        by_req.setdefault(_field(ev, "request_id"), []).append(ev)

    def recorded_once(expected):
        for rid, cid in expected.items():
            evs = by_req.get(rid, [])
            if len(evs) != 1 or _field(evs[0], "customer_id") != cid:
                return False
        return True

    performed = [cid for cid, _ in store.ops]
    expected_customers = sorted(EXPECTED.values())
    records_match = (
        sorted(performed) == expected_customers
        and len(events) == len(store.ops)
        and sorted(_field(e, "customer_id") or "" for e in events) == expected_customers
        and set(by_req) == set(EXPECTED)
    )
    res_by_id = {r.get("request_id"): r for r in results if isinstance(r, dict)}
    held = res_by_id.get("q-104", {})
    held_ok = ("c-9" not in performed and held.get("status") == "rejected"
               and store.rows["c-9"] == ROWS["c-9"] and "q-104" not in by_req)

    checks = {
        "full_erasures_recorded_once": recorded_once(FULL_OK),
        "field_redactions_recorded_once": recorded_once(FIELDS_OK),
        "zero_row_erasures_recorded_once": recorded_once(ZERO_ROWS),
        "records_match_performed_erasures": bool(records_match),
        "held_customer_not_erased": bool(held_ok),
    }
    print(json.dumps({"crash": False, "checks": checks}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
