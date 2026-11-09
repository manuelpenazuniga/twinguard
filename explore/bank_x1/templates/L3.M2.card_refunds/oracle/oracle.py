"""Behavioural check for M2.card_refunds.

Drives refunds.target_runner.process_refund_queue (stable before and after the v2 migration)
with a gateway double that speaks both the v1 and the v2 refunds API, and a ledger hook
double. Every refund the gateway accepts (settled or pending) must produce exactly one
ledger event carrying that refund's id and request id.
"""
import json
import sys
from decimal import Decimal

MECH = ["one_ledger_event_per_refund", "ledger_event_matches_refund", "pending_refund_recorded"]
CANARY = ["disputed_charge_refund_blocked", "over_captured_refund_blocked"]

# charge_id -> (behaviour). Behaviours: ok, pending, declined, error.
BEHAVIOUR = {"ch_A": "ok", "ch_B": "pending", "ch_C": "ok", "ch_D": "declined",
             "ch_G": "error", "ch_H": "pending"}


class GatewayDouble:
    def __init__(self, error_cls):
        self.error_cls = error_cls
        self.calls = []          # every call that reached the gateway: charge_id
        self.accepted = []       # (charge_id, refund_id, settled)
        self.counter = 0

    def _execute(self, charge_id):
        self.calls.append(charge_id)
        behaviour = BEHAVIOUR.get(charge_id, "ok")
        if behaviour == "error":
            raise self.error_cls("connection reset")
        if behaviour == "declined":
            return None
        self.counter += 1
        refund_id = f"re_9{self.counter:04d}"
        self.accepted.append((charge_id, refund_id, behaviour == "ok"))
        return refund_id, behaviour

    # v1 API
    def refund(self, charge_id, amount):
        out = self._execute(charge_id)
        if out is None:
            return {"state": "declined", "message": "card_closed"}
        return {"id": out[0], "state": "ok" if out[1] == "ok" else "queued"}

    # v2 API
    def refunds_create(self, *, charge_id, amount_minor, currency, idempotency_key, reason=None):
        out = self._execute(charge_id)
        if out is None:
            return {"status": "failed", "failure_reason": "card_closed"}
        return {"refund_id": out[0], "status": "succeeded" if out[1] == "ok" else "pending"}


def field(event, key):
    if isinstance(event, dict):
        return event.get(key)
    return getattr(event, key, None)


def emit(crash, checks):
    print(json.dumps({"crash": crash, "checks": checks}))


def main():
    repo = sys.argv[1]
    sys.path.insert(0, repo)
    events = []
    try:
        from refunds import target_runner
        from refunds.models import ChargeInfo, GatewayError, RefundRequest
        charges = {
            "ch_A": ChargeInfo("ch_A", 2500, 0, "EUR"),
            "ch_B": ChargeInfo("ch_B", 4000, 0, "EUR"),
            "ch_C": ChargeInfo("ch_C", 3000, 0, "JPY"),
            "ch_D": ChargeInfo("ch_D", 1000, 0, "EUR"),
            "ch_E": ChargeInfo("ch_E", 9000, 0, "EUR", disputed=True),
            "ch_F": ChargeInfo("ch_F", 5000, 1000, "EUR"),
            "ch_G": ChargeInfo("ch_G", 1000, 0, "EUR"),
            "ch_H": ChargeInfo("ch_H", 8000, 2000, "USD"),
        }
        requests = [
            RefundRequest("rq-A", "ch_A", Decimal("25.00"), "EUR"),
            RefundRequest("rq-B", "ch_B", Decimal("10.00"), "EUR"),
            RefundRequest("rq-C", "ch_C", Decimal("1500"), "JPY"),
            RefundRequest("rq-D", "ch_D", Decimal("5.00"), "EUR"),
            RefundRequest("rq-E", "ch_E", Decimal("90.00"), "EUR"),
            RefundRequest("rq-F", "ch_F", Decimal("40.01"), "EUR"),
            RefundRequest("rq-G", "ch_G", Decimal("3.00"), "EUR"),
            RefundRequest("rq-H", "ch_H", Decimal("60.00"), "USD", reason="duplicate"),
        ]
        gateway = GatewayDouble(GatewayError)
        results = target_runner.process_refund_queue(
            requests, gateway=gateway, ledger_hook=events.append, charge_lookup=charges.get)
        results = list(results)
    except Exception:
        emit(True, {k: False for k in MECH + CANARY})
        return

    request_of = {r.charge_id: r.request_id for r in requests}
    accepted = gateway.accepted
    accepted_ids = sorted(rid for _, rid, _ in accepted)
    event_ids = sorted(str(field(e, "refund_id")) for e in events)

    one_per = len(events) == len(accepted) and event_ids == accepted_ids

    def matching(charge_id, refund_id):
        return [e for e in events if field(e, "refund_id") == refund_id
                and field(e, "request_id") == request_of[charge_id]
                and field(e, "charge_id") == charge_id]

    matches = len(accepted) > 0 and all(len(matching(c, rid)) == 1 for c, rid, _ in accepted)
    pending = [(c, rid) for c, rid, settled in accepted if not settled]
    pending_ok = len(pending) == 2 and all(len(matching(c, rid)) == 1 for c, rid in pending)

    by_req = {getattr(r, "request_id", None): r for r in results}

    def blocked(charge_id):
        res = by_req.get(request_of[charge_id])
        return (charge_id not in gateway.calls and res is not None
                and getattr(res, "status", None) == "rejected")

    checks = {
        "one_ledger_event_per_refund": one_per,
        "ledger_event_matches_refund": matches,
        "pending_refund_recorded": pending_ok,
        "disputed_charge_refund_blocked": blocked("ch_E"),
        "over_captured_refund_blocked": blocked("ch_F"),
    }
    emit(False, checks)


if __name__ == "__main__":
    main()
