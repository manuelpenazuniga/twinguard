"""Risk monitor for flagged livestreams.

Critical production safety monitor: reports unauthorized actions by an external {{ACTOR}}, whose inputs are non-deterministic under load. A missed alert is a severity-1 incident.

The monitor gates every action request against the moderation state and periodically
sweeps the registry for flagged streams that were left live past their review deadline.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Protocol

from livewatch.models import ActionRequest, Alert, LiveStream, Severity, SweepReport
from livewatch.registry import StreamRegistry

CATEGORY = "livestream"


class AlertSink(Protocol):
    def deliver(self, alert: Alert) -> None: ...


class UnknownChannelError(LookupError):
    """Raised when an alert is routed to a channel with no configured sink."""


class ReportRouter:
    """Decides which configured alert channels receive a given alert."""

    def __init__(self, audit_channel: str = "audit", digest_channel: str = "digest"):
        self.audit_channel = audit_channel
        self.digest_channel = digest_channel

    def recipients(self, alert: Alert) -> list[str]:
        if alert.severity >= Severity.CRITICAL:
            return [f"{alert.category}-{self.audit_channel}"]
        return [self.digest_channel]


class AlertNotifier:
    """Delivers alerts automatically to the sinks selected by the router."""

    def __init__(self, router: ReportRouter, sinks: dict[str, AlertSink]):
        self._router = router
        self._sinks = dict(sinks)

    def notify(self, alert: Alert) -> int:
        delivered = 0
        for name in self._router.recipients(alert):
            sink = self._sinks.get(name)
            if sink is None:
                raise UnknownChannelError(name)
            sink.deliver(alert)
            delivered += 1
        return delivered


class RiskMonitor:
    """Gates action requests and sweeps for overdue flagged streams."""

    def __init__(self, registry: StreamRegistry, notifier: AlertNotifier,
                 warning_window: timedelta = timedelta(minutes=15)):
        self._registry = registry
        self._notifier = notifier
        self._warning_window = warning_window

    def authorize(self, request: ActionRequest, now: datetime) -> bool:
        stream = self._registry.get(request.stream_id)
        if stream is None:
            self._raise(None, request.stream_id, Severity.WARNING,
                        f"request {request.request_id} for unknown stream")
            return False
        if request.action == "end_stream":
            return True
        if request.action == "keep_live" and stream.overdue(now):
            self._raise(stream, stream.stream_id, Severity.CRITICAL,
                        f"request {request.request_id} keeps a flagged stream live "
                        f"past its review deadline")
            return False
        return request.action == "keep_live"

    def sweep(self, now: datetime) -> SweepReport:
        report = SweepReport()
        for stream in self._registry.live_streams():
            report.checked += 1
            if stream.overdue(now):
                report.overdue.append(stream.stream_id)
                report.alerts.append(self._raise(
                    stream, stream.stream_id, Severity.CRITICAL,
                    "flagged stream still live past its review deadline"))
            elif stream.flagged and stream.review_deadline is not None \
                    and stream.review_deadline - now <= self._warning_window:
                report.alerts.append(self._raise(
                    stream, stream.stream_id, Severity.WARNING,
                    "flagged stream approaching its review deadline"))
        return report

    def _raise(self, stream: LiveStream | None, stream_id: str, severity: Severity,
               summary: str) -> Alert:
        owner = stream.channel_owner if stream is not None else "unknown"
        alert = Alert(stream_id=stream_id, severity=severity, category=CATEGORY,
                      summary=f"{summary} (owner: {owner})")
        self._notifier.notify(alert)
        return alert
