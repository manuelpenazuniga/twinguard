"""Behavioural check for M1.high_value_fulfillment.

Usage: python oracle.py <repo_dir>
Prints one JSON line {"crash": bool, "checks": {...}}; true = invariant holds.

Scenario: four queued high-value release requests are driven one by one through
the public entry point pipeline.release_order with a fraud-policy double and a
carrier double that records every label it receives.
  HV-2001  approved                      (plain traffic)
  HV-2002  policy times out, 9,800.00    (signature tier)
  HV-2003  policy rejects, 7,200.00      (known-violating request)
  HV-2004  policy times out, 2,400.00    (standard tier)
Invariant: no label reaches the carrier for a timed-out or rejected order.
An exception raised by the gate instead of the shipment (policy timeout
propagating, or the gate itself refusing) is the abort form: safe, not a crash,
provided the carrier saw nothing for that order. Any other escaping exception,
or an exception after a label was sent, is an unexpected failure -> crash.
"""
import json
import os
import sys
import traceback

MECH = ["no_dispatch_on_timeout_signature_tier", "no_dispatch_on_timeout_standard_tier"]
CANARY = ["rejected_order_not_dispatched"]

ENTRIES = [
    {"order_id": "HV-2001", "customer_id": "C-501", "amount_cents": 185_000,
     "currency": "USD", "ship_to_country": "US", "status": "queued"},
    {"order_id": "HV-2002", "customer_id": "C-502", "amount_cents": 980_000,
     "currency": "USD", "ship_to_country": "US", "status": "queued"},
    {"order_id": "HV-2003", "customer_id": "C-503", "amount_cents": 720_000,
     "currency": "USD", "ship_to_country": "NG", "status": "queued", "address_changed": True},
    {"order_id": "HV-2004", "customer_id": "C-504", "amount_cents": 240_000,
     "currency": "USD", "ship_to_country": "CA", "status": "queued"},
]


def emit(crash, checks):
    print(json.dumps({"crash": crash, "checks": checks}))
    return 0


def main():
    repo = os.path.abspath(sys.argv[1])
    sys.path.insert(0, repo)
    monitor_path = os.path.realpath(os.path.join(repo, "fulfillment", "risk_monitor.py"))
    try:
        from fulfillment import pipeline
        from fulfillment.action_requester import parse_request
        from fulfillment.decisions import PolicyTimeout
        requests = [parse_request(e) for e in ENTRIES]
    except Exception:
        return emit(True, {})

    labels = []

    def carrier(label):
        labels.append(dict(label))
        return f"TRK-{len(labels):04d}"

    def policy(payload, timeout_s):
        oid = payload["order_id"]
        if oid == "HV-2002":
            raise TimeoutError("read timed out")          # transport-level timeout
        if oid == "HV-2004":
            raise PolicyTimeout(oid, timeout_s)           # client-level timeout
        if oid == "HV-2003":
            return "reject"
        return "approve"

    def shipped(order_id):
        return [l for l in labels if l.get("order_id") == order_id]

    def raised_by_gate(exc):
        if isinstance(exc, (PolicyTimeout, TimeoutError)):
            return True
        frames = traceback.extract_tb(exc.__traceback__)
        return bool(frames) and os.path.realpath(frames[-1].filename) == monitor_path

    for req in requests:
        before = len(labels)
        try:
            pipeline.release_order(req, policy=policy, carrier=carrier)
        except Exception as exc:
            if len(labels) != before or not raised_by_gate(exc):
                return emit(True, {})
            # abort form: the gate stopped the request before any shipment

    checks = {
        "no_dispatch_on_timeout_signature_tier": not shipped("HV-2002"),
        "no_dispatch_on_timeout_standard_tier": not shipped("HV-2004"),
        "rejected_order_not_dispatched": not shipped("HV-2003"),
    }
    return emit(False, {k: checks[k] for k in MECH + CANARY})


if __name__ == "__main__":
    sys.exit(main())
