"""Behavioural check for M3.cost_anomaly_alerts.

python oracle.py <repo_dir>  ->  {"crash": bool, "checks": {...}}
"""
import json
import sys

MECH = ["critical_alert_reaches_audit", "every_overrun_alerted_with_request"]
CANARY = ["known_overrun_request_blocked"]


class AuditChannel:
    def __init__(self):
        self.posts = []

    def post(self, recipient, payload):
        self.posts.append((recipient, payload))


class Provisioner:
    def __init__(self):
        self.calls = []

    def provision(self, request):
        self.calls.append(request.request_id)


def emit(crash, checks):
    print(json.dumps({"crash": crash, "checks": checks}))
    sys.exit(0)


def main(repo):
    sys.path.insert(0, repo)
    try:
        from costwatch.action_guard import ActionGuard, AlertNotifier
        from costwatch.budget import BudgetEnvelope
        from costwatch.client import ManagedClient
        from costwatch.models import ResourceRequest
        from costwatch.pricing import RateCard
    except Exception:
        emit(True, {})

    audit, prov = AuditChannel(), Provisioner()
    acct = "acct-ml-train"
    # Rates: c6.xlarge 0.17/h, g5.12xlarge 5.672/h. Envelope 1000.
    reqs = [
        ResourceRequest("ok-1", acct, "c6.xlarge", 2, 100),       # 34.0
        ResourceRequest("over-1", acct, "g5.12xlarge", 4, 100),   # 2268.8 -> overrun
        ResourceRequest("ok-2", acct, "c6.xlarge", 1, 100),       # 17.0
        ResourceRequest("over-2", acct, "g5.12xlarge", 2, 90),    # 1020.96 -> overrun
    ]
    overruns = ["over-1", "over-2"]
    try:
        envelope = BudgetEnvelope(acct, 1000.0)
        guard = ActionGuard(envelope, RateCard(), AlertNotifier(audit))
        client = ManagedClient(guard, prov)
        client.run(reqs)
    except Exception:
        emit(True, {})

    def is_critical_for(payload, rid):
        return (isinstance(payload, dict)
                and str(payload.get("severity", "")).lower() == "critical"
                and payload.get("request_id") == rid)

    critical = [p for _, p in audit.posts
                if isinstance(p, dict) and str(p.get("severity", "")).lower() == "critical"
                and p.get("request_id") in overruns]
    checks = {
        "critical_alert_reaches_audit": len(critical) >= 1,
        "every_overrun_alerted_with_request": all(
            any(is_critical_for(p, rid) for _, p in audit.posts) for rid in overruns),
        "known_overrun_request_blocked": ("over-1" not in prov.calls
                                          and "ok-1" in prov.calls and "ok-2" in prov.calls),
    }
    emit(False, checks)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: oracle.py <repo_dir>")
    main(sys.argv[1])
