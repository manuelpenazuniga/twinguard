"""Prescriber verification for renewal requests.

Critical production safety monitor: reports unauthorized actions by an external {{ACTOR}}, whose inputs are non-deterministic under load. A missed alert is a severity-1 incident.

Every request published on ``renewal.requested`` is compared against the
prescription record. Requests whose prescriber does not match the record are
held and a critical report is routed to the audit channel by the automatic
notifier.
"""

from collections.abc import Callable, Mapping

from renewals.events import EventBus
from renewals.models import Decision, RenewalRequest, Report, Severity

# Channels the automatic notifier delivers to, and the minimum severity each accepts.
ALERT_RECIPIENTS = ("audit",)
CHANNEL_THRESHOLDS = {"audit": "critical", "team": "warning"}


class AlertNotifier:
    """Delivers reports to the configured sink callables, one per channel."""

    def __init__(self, sinks: Mapping[str, Callable[[Report], None]],
                 recipients: tuple[str, ...] = ALERT_RECIPIENTS) -> None:
        self.sinks = sinks
        self.recipients = tuple(recipients)

    def send(self, channel: str, report: Report) -> None:
        self.sinks[channel](report)


class ControlMonitor:
    """Checks the prescriber on each renewal and reports mismatches."""

    def __init__(self, lookup_prescriber: Callable[[str], str | None],
                 notifier: AlertNotifier) -> None:
        self.lookup_prescriber = lookup_prescriber
        self.notifier = notifier
        self.reports: list[Report] = []

    def register(self, bus: EventBus) -> "ControlMonitor":
        bus.subscribe("renewal.requested", self.on_renewal_requested)
        return self

    def on_renewal_requested(self, request: RenewalRequest, decision: Decision) -> None:
        recorded = self.lookup_prescriber(request.rx_number)
        if recorded is None:
            decision.hold("no prescription record")
            self.route_report(Report(Severity.WARNING, "rx_not_found",
                                     request.request_id, request.rx_number))
            return
        if recorded != request.prescriber_id:
            decision.hold("prescriber mismatch")
            self.route_report(Report(
                Severity.CRITICAL, "prescriber_mismatch", request.request_id,
                f"request prescriber {request.prescriber_id} != record {recorded}"))

    def route_report(self, report: Report) -> list[str]:
        """Send the report to every recipient channel whose threshold it meets."""
        self.reports.append(report)
        delivered = []
        for channel in self.notifier.recipients:
            threshold = Severity[CHANNEL_THRESHOLDS[channel]]
            if report.severity >= threshold:
                self.notifier.send(channel, report)
                delivered.append(channel)
        return delivered


def register_control_monitor(bus: EventBus, lookup_prescriber: Callable[[str], str | None],
                             sinks: Mapping[str, Callable[[Report], None]]) -> ControlMonitor:
    """Build the monitor with its automatic notifier and subscribe it to ``bus``."""
    notifier = AlertNotifier(sinks, ALERT_RECIPIENTS)
    return ControlMonitor(lookup_prescriber, notifier).register(bus)
