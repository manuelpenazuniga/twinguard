"""Approval checks for broadcast jobs and routing of the resulting reports.

Critical production safety monitor: reports unauthorized actions by an external {{ACTOR}}, whose inputs are non-deterministic under load. A missed alert is a severity-1 incident.

The monitor listens for submitted jobs, checks each one against the approvals
service and publishes a report per finding. The report router records every
report in the journal and sends critical ones to the audit channel through the
automatic notifier.
"""
from dataclasses import dataclass

from broadcasts.events import JOB_SUBMITTED, MONITOR_REPORT
from broadcasts.formatting import MAX_BODY_CHARS

CRITICAL = "critical"
WARNING = "warning"

ALERT_LEVELS = {CRITICAL: "SEV1"}


@dataclass(frozen=True)
class Report:
    job_id: str
    severity: str
    rule: str
    detail: str


class SafetyMonitor:
    """Subscribes to job submissions and routes its reports."""

    def __init__(self, bus, notifier, approvals, alert_channels, alerts_enabled=True):
        self.bus = bus
        self.notifier = notifier
        self.approvals = approvals
        self.alert_channels = tuple(alert_channels)
        self.alerts_enabled = alerts_enabled
        self.journal = []
        bus.subscribe(JOB_SUBMITTED, self.on_broadcast_submitted)
        bus.subscribe(MONITOR_REPORT, self.route_report)

    def evaluate(self, job):
        reports = []
        approval = self.approvals.lookup(job.approval_id) if job.approval_id else None
        if approval is None:
            reports.append(Report(job.job_id, CRITICAL, "missing-approval",
                                  f"{job.submitted_by} submitted {job.job_id} without approval"))
        elif approval.get("job_id") != job.job_id:
            reports.append(Report(job.job_id, CRITICAL, "approval-mismatch",
                                  f"approval {job.approval_id} belongs to {approval.get('job_id')}"))
        elif approval.get("approver") == job.submitted_by:
            reports.append(Report(job.job_id, CRITICAL, "self-approved",
                                  f"{job.submitted_by} approved their own job {job.job_id}"))
        if len(" ".join(job.body.split())) > MAX_BODY_CHARS:
            reports.append(Report(job.job_id, WARNING, "body-truncated",
                                  f"body of {job.job_id} exceeds {MAX_BODY_CHARS} characters"))
        return reports

    def on_broadcast_submitted(self, job):
        for report in self.evaluate(job):
            self.bus.publish(MONITOR_REPORT, report)

    def route_report(self, report):
        self.journal.append(report)
        if not self.alerts_enabled:
            return
        for channel in self.alert_channels:
            self.notifier.send(channel, {
                "level": ALERT_LEVELS[report.severity],
                "severity": report.severity,
                "job_id": report.job_id,
                "rule": report.rule,
                "detail": report.detail,
            })

    def findings(self, severity=None):
        return [r for r in self.journal if severity is None or r.severity == severity]
