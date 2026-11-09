"""Wiring for the broadcast pipeline."""
from dataclasses import dataclass

from broadcasts.events import EventBus
from broadcasts.executor import ExternalExecutor
from broadcasts.safety_monitor import SafetyMonitor

AUDIT_CHANNEL = "#notices-audit"


@dataclass
class Pipeline:
    bus: EventBus
    executor: ExternalExecutor
    monitor: SafetyMonitor

    def run(self, queue):
        return self.executor.run(queue)


def build_pipeline(transport, notifier, approvals, audit_channel=AUDIT_CHANNEL):
    """Create a bus, register the monitor handlers and return the pipeline.

    ``transport`` sends notices (``send(audience, subject, body)``), ``notifier``
    delivers monitor alerts (``send(channel, payload)``) and ``approvals`` resolves
    approval ids (``lookup(approval_id)`` -> dict or None).
    """
    bus = EventBus()
    monitor = SafetyMonitor(bus, notifier, approvals, alert_channels=[audit_channel])
    executor = ExternalExecutor(bus, transport)
    return Pipeline(bus=bus, executor=executor, monitor=monitor)
