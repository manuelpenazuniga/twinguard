"""Wiring for the moderation queue worker."""
from moderation.compliance_check import register_compliance_check
from moderation.events import WILDCARD, EventBus
from moderation.managed_client import ManagedClient
from moderation.notifier import ChannelNotifier


def build_pipeline(store, transport, messenger, metrics=None):
    bus = EventBus()
    register_compliance_check(bus, ChannelNotifier(transport))
    if metrics is not None:
        bus.subscribe(WILDCARD, metrics.record)
    return ManagedClient(bus, store, messenger)
