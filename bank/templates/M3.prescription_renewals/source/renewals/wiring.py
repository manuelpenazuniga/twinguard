"""Assembles the renewal pipeline from its injected collaborators."""
from dataclasses import dataclass

from renewals.control_monitor import AuditNotifier, ControlMonitor
from renewals.events import EventBus
from renewals.monitored_actor import MonitoredActor
from renewals.pharmacy import PharmacyDispatcher


@dataclass
class Pipeline:
    bus: EventBus
    actor: MonitoredActor
    monitor: ControlMonitor
    dispatcher: PharmacyDispatcher


def build_pipeline(registry, gateway, audit_sink, queue=None):
    """Wire intake, prescriber checks and pharmacy hand-off on a fresh bus."""
    bus = EventBus()
    monitor = ControlMonitor(bus, registry, AuditNotifier(audit_sink))
    dispatcher = PharmacyDispatcher(bus, gateway)
    actor = MonitoredActor(bus, queue)
    return Pipeline(bus, actor, monitor, dispatcher)
