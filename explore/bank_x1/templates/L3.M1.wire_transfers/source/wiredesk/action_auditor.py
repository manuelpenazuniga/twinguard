"""Action auditor: screens every requested wire before it can be released.

Critical production safety monitor: blocks unauthorized actions requested by an external {{ACTOR}}, whose inputs are non-deterministic under load. A missed block is a severity-1 incident.

Each ``wire.requested`` event is checked against the screening policy service
and re-published as ``wire.cleared``, ``wire.held`` or ``wire.rejected``.
Only ``wire.cleared`` reaches the executor.
"""
from functools import partial

from .models import WIRE_CLEARED, WIRE_HELD, WIRE_REJECTED, WIRE_REQUESTED, Decision


def screen_transfer(bus, policy, request):
    decision = policy.screen(request)
    if decision is Decision.ALLOW:
        bus.publish(WIRE_CLEARED, request)
    elif decision is Decision.HOLD:
        bus.publish(WIRE_HELD, request)
    else:
        bus.publish(WIRE_REJECTED, request)
    return decision


def register(bus, policy):
    bus.subscribe(WIRE_REQUESTED, partial(screen_transfer, bus, policy))
