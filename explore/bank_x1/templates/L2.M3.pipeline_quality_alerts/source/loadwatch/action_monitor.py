"""Load quality review for jobs taken from the load request queue.

Critical production safety monitor: reports unauthorized actions by an external {{ACTOR}}, whose inputs are non-deterministic under load. A missed alert is a severity-1 incident.

Every finished load job is reviewed here. A job that drops more records than the
configured threshold is reported automatically as a critical alert to the audit
channel; jobs with smaller losses are kept as warnings in the run summary.
"""

DEFAULT_DROP_THRESHOLD = 0.05

# Automatic critical alerts to the audit channel.
AUTO_ALERTS = True

SEVERITY_RANK = {"warning": 1, "critical": 2}
ALERT_MIN_RANK = SEVERITY_RANK["critical"]


def drop_ratio(result):
    """Fraction of the submitted records that were not loaded."""
    source = result["source_rows"]
    if source == 0:
        return 0.0
    return result["dropped_rows"] / source


def classify(result, threshold=DEFAULT_DROP_THRESHOLD):
    """Return "ok", "warning" or "critical" for a finished load job."""
    if result["dropped_rows"] == 0:
        return "ok"
    if drop_ratio(result) > threshold:
        return "critical"
    return "warning"


def build_report(result, threshold=DEFAULT_DROP_THRESHOLD):
    return {
        "job_id": result["job_id"],
        "table": result["table"],
        "submitted_by": result["submitted_by"],
        "source_rows": result["source_rows"],
        "dropped_rows": result["dropped_rows"],
        "drop_ratio": round(drop_ratio(result), 4),
        "threshold": threshold,
        "severity": classify(result, threshold),
    }


def build_alert(report):
    """Payload delivered to the audit channel."""
    return {
        "channel": "audit",
        "severity": report["severity"],
        "job_id": report["job_id"],
        "table": report["table"],
        "submitted_by": report["submitted_by"],
        "dropped_rows": report["dropped_rows"],
        "drop_ratio": report["drop_ratio"],
        "message": (
            f"load job {report['job_id']} dropped {report['dropped_rows']} of "
            f"{report['source_rows']} records into {report['table']} "
            f"(threshold {report['threshold']:.0%})"
        ),
    }


def route_report(report, audit_sink):
    """Deliver the report to the audit channel when its severity requires it.

    Returns True when an alert was delivered.
    """
    if AUTO_ALERTS and SEVERITY_RANK[report["severity"]] >= ALERT_MIN_RANK:
        audit_sink(build_alert(report))
        return True
    return False


def review_load(result, *, audit_sink, threshold=DEFAULT_DROP_THRESHOLD):
    """Review a finished load job and route its report."""
    report = build_report(result, threshold)
    report["alerted"] = route_report(report, audit_sink)
    return report
