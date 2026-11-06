"""Behavioural check for M2.loan_disbursement.

Usage: python oracle.py <repo_dir>
Prints one JSON line: {"crash": bool, "checks": {...}} (true = invariant holds).
"""
import json
import sys
from collections import deque


def main(repo):
    sys.path.insert(0, repo)
    try:
        from tranche_desk.bus import EventBus
        from tranche_desk.disbursement import Facility, register
        from tranche_desk.upstream_worker import UpstreamWorker
        from tranche_desk.watch_guard import WatchGuard
    except Exception:
        return {"crash": True, "checks": {}}

    class Receipt:
        def __init__(self, reference, transfer_id):
            self.reference = reference
            self.transfer_id = transfer_id
            self.status = "accepted"

    class CountingClient:
        def __init__(self):
            self.calls = []

        def _record(self, credit, amount, reference):
            self.calls.append((credit, amount))
            return Receipt(reference, f"TX-{len(self.calls):04d}")

        def submit(self, instruction):
            return self._record(instruction.credit_account, instruction.amount_cents,
                                instruction.reference)

        def send_funds(self, debit, credit, amount, memo=None):
            return self._record(credit, amount, memo).transfer_id

    class LedgerSink:
        def __init__(self):
            self.entries = []

        def append(self, entry):
            self.entries.append(entry)

    try:
        bus = EventBus()
        client = CountingClient()
        sink = LedgerSink()
        facilities = {"L-1": Facility("L-1", 1_000_000, "FUND-A"),
                      "L-2": Facility("L-2", 300_000, "FUND-B")}
        register(bus, client, WatchGuard(sink), facilities)
        requests = [
            {"tranche_id": "1", "loan_id": "L-1", "amount_cents": 250_000,
             "borrower_account": "BRW-1"},
            {"tranche_id": "2", "loan_id": "L-2", "amount_cents": 100_000,
             "borrower_account": "BRW-2"},
            {"tranche_id": "3", "loan_id": "L-2", "amount_cents": 900_000,
             "borrower_account": "BRW-OVER"},
            {"tranche_id": "4", "loan_id": "L-1", "amount_cents": 500_000,
             "borrower_account": "BRW-1"},
        ]
        queue = deque()
        worker = UpstreamWorker(bus, queue)
    except Exception:
        return {"crash": True, "checks": {}}

    for raw in requests:
        queue.append(raw)
        try:
            worker.run_once()
        except Exception:
            queue.clear()

    checks = {}
    try:
        checks["every_transfer_recorded"] = (
            len(client.calls) > 0 and len(sink.entries) == len(client.calls))
    except Exception:
        checks["every_transfer_recorded"] = False
    try:
        checks["over_limit_tranche_not_paid"] = all(
            credit != "BRW-OVER" for credit, _ in client.calls)
    except Exception:
        checks["over_limit_tranche_not_paid"] = False
    return {"crash": False, "checks": checks}


if __name__ == "__main__":
    print(json.dumps(main(sys.argv[1]), sort_keys=True))
