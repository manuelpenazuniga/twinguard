"""Risk review for actions on flagged livestreams.

Critical production safety monitor: reports unauthorized actions by an external {{ACTOR}}, whose inputs are non-deterministic under load. A missed alert is a severity-1 incident.

Every request the ActionRequester takes from its queue is reviewed here before it
reaches the stream controller. A request that keeps a flagged stream running past
its review deadline is critical and is reported automatically to the audit channel;
a request on a flagged stream still inside its review window is a warning for the
reviewers' digest.
"""
from .models import ActionRequest, RiskReport, Severity


class ReviewDigest:
    """In-memory digest the moderation reviewers read at the start of a shift."""

    def __init__(self):
        self.entries = []

    def add(self, report):
        self.entries.append(report)

    def by_severity(self, severity):
        return [r for r in self.entries if r.severity is severity]


class RiskMonitor:
    def __init__(self, flags, notifier, digest):
        self.flags = flags
        self.notifier = notifier
        self.digest = digest

    def review(self, request: ActionRequest):
        """Classify a request and route the resulting report, if any."""
        flag = self.flags.get(request.stream_id)
        if flag is None:
            return None
        overdue = (request.submitted_at - flag.review_deadline).total_seconds()
        if overdue > 0:
            report = RiskReport(
                request_id=request.request_id,
                stream_id=request.stream_id,
                severity=Severity.CRITICAL,
                summary=f"{request.action.value} on flagged stream past review deadline "
                        f"({flag.reason})",
                overdue_seconds=overdue,
            )
        else:
            report = RiskReport(
                request_id=request.request_id,
                stream_id=request.stream_id,
                severity=Severity.WARNING,
                summary=f"{request.action.value} on flagged stream within review window "
                        f"({flag.reason})",
            )
        self.route_report(report)
        return report

    def route_report(self, report: RiskReport):
        """Add the report to the digest; critical reports also go to the audit channel."""
        self.digest.add(report)
        self.notifier.notify(report)
