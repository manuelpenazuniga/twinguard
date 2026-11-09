"""Assembles the wire desk on an event bus and runs one queue cycle."""
from . import action_auditor, external_executor
from .events import EventBus
from .models import WIRE_HELD, WIRE_REJECTED, WIRE_SENT, RunSummary


def build_desk(policy, gateway, summary=None):
    """Return ``(bus, summary)`` with all handlers registered.

    ``policy`` must provide ``screen(request) -> Decision``; ``gateway`` must
    provide ``send(instruction)``.
    """
    bus = EventBus()
    summary = summary if summary is not None else RunSummary()
    action_auditor.register(bus, policy)
    external_executor.register(bus, gateway)
    bus.subscribe(WIRE_SENT, lambda request: summary.sent.append(request.request_id))
    bus.subscribe(WIRE_HELD, lambda request: summary.held.append(request.request_id))
    bus.subscribe(WIRE_REJECTED, lambda request: summary.rejected.append(request.request_id))
    return bus, summary


def process_queue(policy, gateway, requests):
    """Screen and release every request in ``requests``; return the RunSummary."""
    bus, summary = build_desk(policy, gateway)
    external_executor.submit_queue(bus, requests)
    return summary
