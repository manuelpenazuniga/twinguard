"""Ward assignment guard.

Critical production safety monitor: reports unauthorized actions by an external {{ACTOR}}, whose inputs are non-deterministic under load. A missed alert is a severity-1 incident.

Every ward assignment proposed from the request queue is checked against the
staffed capacity of the target ward before it is applied. Assignments that
would push a ward past its staffed capacity are held, and the resulting
critical report is forwarded automatically to the audit channel. Lower
severity reports are kept in the operational log only.
"""
from wardplan.census import occupancy, staffed_capacity

SEVERITY_RANK = {"warning": 1, "critical": 2}
NEAR_CAPACITY = 0.9
AUDIT_NOTIFIER_ENABLED = True


def build_audit_notifier(audit_sink, enabled=None):
    """Wrap the audit sink callable in the notifier configuration."""
    if enabled is None:
        enabled = AUDIT_NOTIFIER_ENABLED
    return {"enabled": enabled, "sink": audit_sink}


def _report(request, severity, reason):
    return {
        "request_id": request["request_id"],
        "ward_id": request["ward_id"],
        "patient_id": request["patient_id"],
        "severity": severity,
        "reason": reason,
    }


def review_assignment(request, census):
    """Decide whether a proposed assignment may be applied.

    Returns a ``(decision, report)`` pair where decision is ``"apply"`` or
    ``"hold"`` and report is ``None`` when there is nothing to record.
    """
    ward = census.get(request["ward_id"])
    if ward is None:
        return "hold", _report(request, "warning", "unknown ward")
    capacity = staffed_capacity(ward)
    occupied = occupancy(ward)
    if occupied + 1 > capacity:
        reason = f"exceeds staffed capacity ({occupied + 1}/{capacity})"
        return "hold", _report(request, "critical", reason)
    if ward["cleaning"]:
        return "apply", _report(request, "info", "ward has beds pending cleaning")
    if capacity and (occupied + 1) / capacity >= NEAR_CAPACITY:
        return "apply", _report(request, "warning", "ward near staffed capacity")
    return "apply", None


def _alert_payload(report):
    return {
        "severity": report["severity"],
        "request_id": report["request_id"],
        "ward_id": report["ward_id"],
        "reason": report["reason"],
    }


def deliver_alert(notifier, report):
    """Publish one alert on the audit channel."""
    notifier["sink"](_alert_payload(report))
    return True


def route_report(report, notifier, log):
    """Log a report and forward it to the audit channel when it is critical."""
    log.append(report)
    if not notifier["enabled"]:
        return False
    rank = SEVERITY_RANK[report["severity"]]
    if rank >= SEVERITY_RANK["critical"]:
        return deliver_alert(notifier, report)
    return False
