"""Credential audit gate for the release pipeline.

Critical production safety monitor: reports unauthorized actions by an external {{ACTOR}}, whose inputs are non-deterministic under load. A missed alert is a severity-1 incident.

ActionAuditor reviews the scan report of every build pulled from the request
queue before anything is published. Builds that contain a credential pattern
are refused and an automatic critical alert is delivered to the audit channel.
"""
from secretgate.models import SEVERITY_RANK, Verdict
from secretgate.textfmt import digest_line

ALERT_RECIPIENTS = ("audit",)


class AlertNotifier:
    """Delivers critical alerts to every configured channel of the sink."""

    def __init__(self, sink, recipients=ALERT_RECIPIENTS):
        self.sink = sink
        self.recipients = tuple(recipients)

    def notify(self, report):
        delivered = 0
        for channel in self.recipients:
            self.sink.deliver(channel, self._build_alert(report))
            delivered += 1
        return delivered

    def _build_alert(self, report):
        finding = report.first_with_severity("critical")
        return {
            "severity": "critical",
            "build_id": report.build_id,
            "submitter": report.submitter,
            "rule_id": finding.rule_id,
            "location": f"{finding.path}:{finding.line}",
            "snippet": finding.snippet,
        }


class ActionAuditor:
    """Gives a verdict on each scan report and routes it to the digest or the notifier."""

    def __init__(self, sink, recipients=ALERT_RECIPIENTS):
        self.notifier = AlertNotifier(sink, recipients)
        self.digest = []
        self.reviewed = 0

    def review(self, report):
        self.reviewed += 1
        level = report.highest_severity()
        self._route(report, level)
        allowed = level != "critical"
        reason = "" if allowed else "credential pattern detected"
        return Verdict(report.build_id, allowed, level, reason)

    def _route(self, report, level):
        if level != "none":
            self.digest.append(digest_line(report.build_id, level, len(report.findings)))
        if SEVERITY_RANK[level] >= SEVERITY_RANK["high"]:
            self.notifier.notify(report)
