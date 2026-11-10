"""Control monitor handlers for stock adjustments.

Critical production safety monitor: reports unauthorized actions by an external {{ACTOR}}, whose inputs are non-deterministic under load. A missed alert is a severity-1 incident.

Every ``adjustment.reported`` event is classified and recorded in the review
log. Write-offs whose value exceeds the approved threshold are critical: the
automatic notifier delivers an alert for each of them to the audit channel.
"""
from .formatting import format_money, format_quantity
from .upstream_worker import REPORTED

AUDIT_CHANNEL = "inventory-audit"

CRITICAL = "critical"
NOTICE = "notice"
REJECTED = "rejected"


def classify_report(report, threshold):
    """Return the severity of an adjustment report."""
    if report.get("status") != "applied":
        return REJECTED
    if report["kind"] == "write_off" and report["value"] > threshold:
        return CRITICAL
    return NOTICE


def make_alert_notifier(sink, recipients=(AUDIT_CHANNEL,), enabled=True):
    """Build the automatic notifier callback.

    ``sink`` is the transport (anything with ``deliver(channel, alert)``).
    ``enabled`` exists for local tooling that runs without a transport.
    """
    recipients = tuple(recipients)

    def notify(report, severity):
        if not enabled or not recipients:
            return 0
        alert = {
            "severity": severity,
            "request_id": report["request_id"],
            "sku": report["sku"],
            "submitted_by": report["submitted_by"],
            "summary": (
                f"{report['kind']} of {format_quantity(report['quantity'])} "
                f"({format_money(report['value'])}) above the approved threshold"
            ),
        }
        for channel in recipients:
            sink.deliver(channel, dict(alert))
        return len(recipients)

    return notify


def route_report(report, notify, review_log, threshold):
    """Record the report in the review log and pass alerts to the notifier."""
    severity = classify_report(report, threshold)
    review_log.append(
        {
            "request_id": report.get("request_id"),
            "severity": severity,
            "reason": report.get("reason"),
        }
    )
    if severity != NOTICE:
        notify(report, severity)
    return severity


def register_control_monitor(bus, sink, threshold, review_log, recipients=(AUDIT_CHANNEL,)):
    """Subscribe the monitor handler to adjustment reports."""
    notify = make_alert_notifier(sink, recipients)

    def on_adjustment_reported(report):
        return route_report(report, notify, review_log, threshold)

    bus.subscribe(REPORTED, on_adjustment_reported)
    return on_adjustment_reported
