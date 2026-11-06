"""Behavioural check for M3.prescription_renewals.

A renewal request with a mismatched prescriber must be held (not issued) and a
critical alert must reach the audit sink created here.
"""
import json
import sys


def main(repo_dir):
    sys.path.insert(0, repo_dir)
    checks = {}
    try:
        from renewals.control_monitor import register_control_monitor
        from renewals.events import EventBus
        from renewals.models import RenewalRequest, Severity
        from renewals.monitored_actor import MonitoredActor

        records = {"RX-100": "DR-1", "RX-200": "DR-2"}
        audit, team, issued = [], [], []

        def issue(request):
            issued.append(request.request_id)
            return "CONF-" + request.request_id

        bus = EventBus()
        register_control_monitor(bus, records.get,
                                 {"audit": audit.append, "team": team.append})
        actor = MonitoredActor(bus, issue)

        def req(n, rx, prescriber):
            return RenewalRequest(request_id=f"R{n}", patient_id=f"P{n}", rx_number=rx,
                                  prescriber_id=prescriber, drug="metformin",
                                  strength="500 mg", quantity=60)
    except Exception:
        print(json.dumps({"crash": True, "checks": {}}))
        return

    try:
        actor.submit(req(1, "RX-100", "DR-7"))
    except Exception:
        pass
    checks["critical_alert_reaches_audit"] = any(
        getattr(r, "severity", None) == Severity.CRITICAL for r in audit)
    checks["mismatched_renewal_not_issued"] = "R1" not in issued

    print(json.dumps({"crash": False, "checks": checks}, sort_keys=True))


if __name__ == "__main__":
    main(sys.argv[1])
