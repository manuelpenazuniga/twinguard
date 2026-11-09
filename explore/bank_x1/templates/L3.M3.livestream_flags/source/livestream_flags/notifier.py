"""Automatic notifier for the trust & safety audit channel."""
from .formatting import format_duration, stream_label
from .models import RiskReport, Severity

AUDIT_CHANNEL = "ts-livestream-audit"


class AuditNotifier:
    """Delivers critical alerts to the audit channel through an injected sink.

    The sink only needs a ``deliver(channel, payload)`` method; production wires the
    chat-ops client, tests use an in-memory list.
    """

    def __init__(self, sink, channel=AUDIT_CHANNEL):
        self.sink = sink
        self.channel = channel

    def notify(self, report: RiskReport):
        if report.severity is not Severity.CRITICAL:
            raise ValueError("audit channel accepts critical alerts only")
        self.sink.deliver(self.channel, self._payload(report))

    def _payload(self, report):
        return {
            "severity": report.severity.value,
            "request_id": report.request_id,
            "stream": stream_label(report.stream_id),
            "summary": report.summary,
            "overdue": format_duration(report.overdue_seconds),
        }
