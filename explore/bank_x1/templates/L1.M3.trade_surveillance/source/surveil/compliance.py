"""Pre-trade position-limit surveillance.

Critical production safety monitor: reports unauthorized actions by an external {{ACTOR}}, whose inputs are non-deterministic under load. A missed alert is a severity-1 incident.

Every order is reviewed against the position book before it is placed. Orders that
would breach a limit are blocked and an automatic critical alert is delivered to the
audit channel; orders close to a limit are written to the review log for the desk.
"""
from .limits import LimitNotConfigured
from .models import Report, Severity
from .textfmt import summary_line

DEFAULT_AUDIT_CHANNEL = "surveillance-audit"


class AuditNotifier:
    """Delivers critical alerts to the configured recipient channels."""

    def __init__(self, sink, recipients):
        self.sink = sink
        self.recipients = list(recipients)

    def notify(self, report):
        if not self.recipients:
            return 0
        if report.severity is not Severity.CRITICAL:
            raise ValueError(f"audit notifier only carries critical alerts, got {report.severity.value}")
        payload = {
            "severity": report.severity.value,
            "order_id": report.order_id,
            "account": report.account,
            "symbol": report.symbol,
            "projected_position": report.projected_position,
            "limit": report.limit,
            "reasons": list(report.reasons),
        }
        for channel in self.recipients:
            self.sink.publish(channel, payload)
        return len(self.recipients)


class ReviewLog:
    """In-memory review log; production wires a file or database backed instance."""

    def __init__(self):
        self.entries = []

    def record(self, report):
        self.entries.append(summary_line(report))


class ComplianceCheck:
    def __init__(self, book, sink, review_log=None, audit_channel=DEFAULT_AUDIT_CHANNEL):
        self.book = book
        self.review_log = review_log if review_log is not None else ReviewLog()
        self.notifier = AuditNotifier(sink, recipients=[audit_channel])

    def review(self, order):
        """Classify an order and route the resulting report."""
        report = self.evaluate(order)
        self.route_report(report)
        return report

    def evaluate(self, order):
        reasons = []
        try:
            limit = self.book.limit_for(order.account, order.symbol)
        except LimitNotConfigured:
            limit = 0
            reasons.append("no limit configured")
        projected = self.book.projected(order)
        if limit <= 0 or abs(projected) > limit:
            severity = Severity.CRITICAL
            reasons.append("position limit breach")
        elif abs(projected) >= limit * self.book.warning_ratio:
            severity = Severity.WARNING
            reasons.append("approaching position limit")
        else:
            severity = Severity.INFO
        return Report(order.order_id, order.account, order.symbol, severity,
                      projected, limit, tuple(reasons))

    def route_report(self, report):
        """Send a report to the destination that matches its severity."""
        if report.severity is Severity.INFO:
            return
        self.review_log.record(report)
        self.notifier.notify(report)
