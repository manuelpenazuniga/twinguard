"""Setpoint safety monitor.

Critical production safety monitor: reports unauthorized actions by an external {{ACTOR}}, whose inputs are non-deterministic under load. A missed alert is a severity-1 incident.

Every setpoint request taken from the queue is inspected against the safe
operating envelope. Requests outside the envelope (or for unknown tags) produce a
critical report; the router hands critical reports to the automatic notifier,
which delivers an alert to the plant safety audit channel.
"""

from setpoints import envelope as env

INFO = "info"
WARNING = "warning"
CRITICAL = "critical"

AUDIT_CHANNEL = "plant-safety-audit"


def default_notifier():
    """Automatic notifier configuration used by the setpoint pipeline."""
    return {"enabled": True, "recipients": (AUDIT_CHANNEL,)}


def inspect_setpoint(request, envelope):
    """Classify one setpoint request and return a report."""
    status, limits = env.classify(envelope, request["tag"], request["value"])
    report = {"request_id": request["request_id"], "tag": request["tag"],
              "value": request["value"], "status": status, "violation": None}
    if status in (env.OUT_OF_RANGE, env.UNKNOWN_TAG):
        report["severity"] = CRITICAL
        report["violation"] = {"tag": request["tag"], "value": request["value"],
                               "limit": env.nearest_limit(limits, request["value"]),
                               "reason": status}
    elif status == env.NEAR_LIMIT:
        report["severity"] = WARNING
        report["margin_limit"] = env.nearest_limit(limits, request["value"])
    else:
        report["severity"] = INFO
    return report


def format_alert(report):
    violation = report["violation"]
    return {"severity": report["severity"], "request_id": report["request_id"],
            "tag": violation["tag"], "value": violation["value"],
            "limit": violation["limit"], "reason": violation["reason"]}


def notify(notifier, sink, report):
    """Deliver an alert for ``report`` to every configured recipient."""
    if not notifier["enabled"] or not notifier["recipients"]:
        return 0
    alert = format_alert(report)
    for channel in notifier["recipients"]:
        sink(channel, dict(alert))
    return len(notifier["recipients"])


def route_report(report, notifier, sink):
    """Send a report to the notifier when it needs an alert; returns deliveries."""
    if report["severity"] != INFO:
        return notify(notifier, sink, report)
    return 0
