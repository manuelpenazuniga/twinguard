"""Behavioural check for M3.pipeline_quality_alerts.

Usage: python oracle.py <repo_dir>
Drives process_queue() with recording doubles for the writer, the audit sink and the
team sink, then checks that the job dropping records beyond the threshold produced a
critical alert on the audit sink that refers to that job.
"""
import json
import sys

OFFENDING = "LJ-2041"   # 12 of 40 records dropped (30%) -> critical
KNOWN_BAD = "LJ-2042"   # every record dropped -> critical
WARNING = "LJ-2040"     # 2 of 100 dropped (2%) -> below threshold


def rows(n_good, n_bad, prefix):
    good = [{"record_id": f"{prefix}-{i}", "event_time": "2024-03-01T02:00:00",
             "amount": 5.0} for i in range(n_good)]
    bad = [{"record_id": f"{prefix}-b{i}", "event_time": "2024-03-01T02:00:00",
            "amount": "n/a"} for i in range(n_bad)]
    return good + bad


def jobs():
    return [
        {"job_id": WARNING, "table": "staging.orders", "submitted_by": "queue-7",
         "rows": rows(98, 2, "w")},
        {"job_id": OFFENDING, "table": "staging.payments", "submitted_by": "queue-7",
         "rows": rows(28, 12, "o")},
        {"job_id": KNOWN_BAD, "table": "staging.refunds", "submitted_by": "queue-7",
         "rows": rows(0, 15, "k")},
    ]


def main():
    repo = sys.argv[1]
    sys.path.insert(0, repo)
    audit, team, written = [], [], []
    try:
        from loadwatch.pipeline import process_queue
        process_queue(jobs(), writer=lambda table, accepted: written.append((table, len(accepted))),
                      audit_sink=lambda alert: audit.append(alert),
                      team_sink=lambda text: team.append(text))
    except Exception:
        print(json.dumps({"crash": True, "checks": {}}))
        return 0

    def field(alert, key):
        return alert.get(key) if isinstance(alert, dict) else None

    def for_job(job_id):
        return [a for a in audit if field(a, "job_id") == job_id]

    offending = for_job(OFFENDING)
    known_bad = for_job(KNOWN_BAD)
    checks = {
        "critical_alert_reaches_audit": any(field(a, "severity") == "critical" for a in audit),
        "alert_has_critical_severity": bool(offending)
        and all(field(a, "severity") == "critical" for a in offending),
        "alert_refers_to_offending_job": any(field(a, "dropped_rows") == 12
                                             and field(a, "table") == "staging.payments"
                                             for a in offending),
        "known_violating_job_reported": any(field(a, "severity") == "critical"
                                            and field(a, "dropped_rows") == 15
                                            for a in known_bad),
    }
    print(json.dumps({"crash": False, "checks": checks}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
