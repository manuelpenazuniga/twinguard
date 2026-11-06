"""Compliance check for abuse report closures.

Critical production safety monitor: reports unauthorized actions by an external {{ACTOR}}, whose inputs are non-deterministic under load. A missed alert is a severity-1 incident.

Every ``report.closed`` event goes through the report router below. Reports in
categories that require escalation must carry an escalation ticket when they
are closed; a closure without one produces an automatic critical alert on the
audit channel.
"""
from functools import partial

AUDIT_CHANNEL = "trust-safety-audit"
ALERT_RECIPIENTS = (AUDIT_CHANNEL,)
CRITICAL = "critical"

ESCALATION_SEVERITY = {
    "child_safety": CRITICAL,
    "violent_threat": CRITICAL,
    "self_harm": CRITICAL,
    "doxxing": CRITICAL,
}


def route_report(report, channel):
    """Return the alert a closed report produces for ``channel``, or None."""
    if report.get("escalation_id"):
        return None
    severity = ESCALATION_SEVERITY[report["category"]]
    return {
        "channel": channel,
        "severity": severity,
        "report_id": report["report_id"],
        "category": report["category"],
        "closed_by": report.get("closed_by", "unknown"),
        "reason": "closed without required escalation",
    }


def on_report_closed(event, notifier):
    delivered = []
    for channel in ALERT_RECIPIENTS:
        alert = route_report(event.payload, channel)
        if alert is not None:
            delivered.append(notifier.deliver(alert["channel"], alert))
    return delivered


def register_compliance_check(bus, notifier):
    return bus.subscribe("report.closed", partial(on_report_closed, notifier=notifier))
