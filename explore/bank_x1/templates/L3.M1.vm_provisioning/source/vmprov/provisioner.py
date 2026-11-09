"""Provisioner: turns approved requests into instances on the compute API."""
from __future__ import annotations

from .events import PROVISION_APPROVED, EventBus
from .models import ProvisionRequest, RunSummary


def provision_vm(request: ProvisionRequest, compute_api) -> list[str]:
    """Create the instances for an approved request and return their ids."""
    return list(compute_api.create_instance(
        request_id=request.request_id,
        project=request.project,
        region=request.region,
        machine_type=request.machine_type,
        count=request.count,
    ))


def register_provisioner(bus: EventBus, compute_api, summary: RunSummary):
    """Subscribe the provisioner to approved events and return its handler."""

    def on_provision_approved(request: ProvisionRequest) -> None:
        instance_ids = provision_vm(request, compute_api)
        summary.provisioned.append(request.request_id)
        summary.instances[request.request_id] = instance_ids

    bus.subscribe(PROVISION_APPROVED, on_provision_approved)
    return on_provision_approved
