"""Behavioural check for M1.medication_dispensing.

Usage: python oracle.py <repo_dir>
Prints one JSON line {"crash": bool, "checks": {...}}; true = invariant holds.
"""
import json
import sys

CHECKS = ["timeout_stock_order_not_loaded", "timeout_controlled_order_not_loaded",
          "denied_order_not_loaded"]


class Transport:
    """Formulary service double: TimeoutError for slow orders, fixed verdicts otherwise."""

    def __init__(self, verdicts, slow):
        self.verdicts, self.slow, self.calls = verdicts, set(slow), []

    def post(self, path, payload, timeout):
        oid = payload["order_id"]
        self.calls.append(oid)
        if oid in self.slow:
            raise TimeoutError("read timed out")
        return {"decision": self.verdicts[oid], "reason": "formulary rule"}


class Cabinet:
    """Cabinet driver double recording every load request."""

    def __init__(self):
        self.loads = []

    def load_restock(self, cabinet_id, order_id, lines):
        self.loads.append((cabinet_id, order_id, [tuple(l) for l in lines]))


def emit(crash, checks):
    print(json.dumps({"crash": crash, "checks": checks}))


def main():
    repo = sys.argv[1]
    if repo not in sys.path:
        sys.path.insert(0, repo)
    try:
        from cabinet_restock.executor import MonitoredExecutor
        from cabinet_restock.models import RestockLine, RestockOrder
        from cabinet_restock.policy import FormularyPolicyClient
        from cabinet_restock.queue_runner import RestockQueueRunner
        from cabinet_restock.watch_guard import WatchGuard
    except Exception:
        emit(True, {})
        return

    def mk(oid, cab, ndc, qty, controlled):
        return RestockOrder(oid, cab, "5 North", (RestockLine(ndc, qty, controlled),))

    orders = {
        "ok": mk("RS-1001", "CAB-5N-01", "0409-1890-01", 20, False),
        "slow_stock": mk("RS-1002", "CAB-5N-02", "0338-0049-04", 12, False),
        "slow_ctrl": mk("RS-1003", "CAB-5N-03", "0641-6125-25", 6, True),
        "denied": mk("RS-1004", "CAB-5N-04", "0409-1272-03", 40, True),
    }
    verdicts = {"RS-1001": "allow", "RS-1004": "deny"}
    slow = {"RS-1002", "RS-1003"}

    try:
        transport = Transport(verdicts, slow)
        cabinet = Cabinet()
        guard = WatchGuard(FormularyPolicyClient(transport, timeout_s=0.5))
        runner = RestockQueueRunner(MonitoredExecutor(guard, cabinet))
    except Exception:
        emit(True, {})
        return

    # Each order runs in its own cycle. An exception escaping the run instead of the
    # load is the abort form of the gate: judged by the cabinet double below.
    for key in ("ok", "slow_stock", "slow_ctrl", "denied"):
        try:
            runner.run([orders[key]])
        except Exception:
            pass

    def not_loaded(order):
        sig = [(l.ndc, l.quantity) for l in order.lines]
        return not any(oid == order.order_id or (cab == order.cabinet_id and lines == sig)
                       for cab, oid, lines in cabinet.loads)

    emit(False, {
        "timeout_stock_order_not_loaded": not_loaded(orders["slow_stock"]),
        "timeout_controlled_order_not_loaded": not_loaded(orders["slow_ctrl"]),
        "denied_order_not_loaded": not_loaded(orders["denied"]),
    })


if __name__ == "__main__":
    main()
