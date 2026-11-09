"""Wiring of the provisioning stages and the queue entry point."""
from __future__ import annotations

from typing import Iterable

from .action_requester import QueueItem, request_actions
from .events import PROVISION_DENIED, PROVISION_HELD, EventBus
from .models import ProvisionRequest, RunSummary
from .provisioner import register_provisioner
from .risk_monitor import register_risk_monitor


def build_bus(policy_client, compute_api, summary: RunSummary) -> EventBus:
    """Create a bus with the monitor, the provisioner and the run ledger attached."""
    bus = EventBus()
    register_risk_monitor(bus, policy_client)
    register_provisioner(bus, compute_api, summary)

    def on_denied(request: ProvisionRequest) -> None:
        summary.denied.append(request.request_id)

    def on_held(request: ProvisionRequest) -> None:
        summary.held.append(request.request_id)

    bus.subscribe(PROVISION_DENIED, on_denied)
    bus.subscribe(PROVISION_HELD, on_held)
    return bus


def process_queue(queue: Iterable[QueueItem], policy_client, compute_api) -> RunSummary:
    """Process every queued request and return the run summary."""
    summary = RunSummary()
    bus = build_bus(policy_client, compute_api, summary)
    request_actions(bus, queue)
    return summary
