"""Wiring for the lab-result release pipeline."""
from labportal.events import EventBus
from labportal.managed_client import ManagedClient
from labportal.release_handlers import register_release_handlers
from labportal.risk_monitor import RiskMonitor


def build_pipeline(portal, audit_hook, hold_policy, bus=None):
    """Return a ManagedClient whose submissions flow through the release handlers."""
    bus = bus if bus is not None else EventBus()
    monitor = RiskMonitor(audit_hook)
    register_release_handlers(bus, portal, monitor, hold_policy)
    return ManagedClient(bus)
