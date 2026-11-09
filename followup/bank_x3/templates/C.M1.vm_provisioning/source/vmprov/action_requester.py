"""Action requester: relays queued provisioning requests onto the event bus."""
from __future__ import annotations

from typing import Iterable, Mapping, Union

from .events import PROVISION_REQUESTED, EventBus
from .models import ProvisionRequest

QueueItem = Union[ProvisionRequest, Mapping[str, object]]

REQUIRED_FIELDS = ("request_id", "project", "region", "machine_type", "vcpus")


def parse_request(raw: Mapping[str, object]) -> ProvisionRequest:
    """Build a request from a raw queue message."""
    missing = [name for name in REQUIRED_FIELDS if name not in raw]
    if missing:
        raise ValueError(f"queue message missing fields: {', '.join(missing)}")
    return ProvisionRequest(
        request_id=str(raw["request_id"]),
        project=str(raw["project"]),
        region=str(raw["region"]),
        machine_type=str(raw["machine_type"]),
        vcpus=int(raw["vcpus"]),
        count=int(raw.get("count", 1)),
    )


def request_actions(bus: EventBus, queue: Iterable[QueueItem]) -> int:
    """Publish one requested event per queue item, in queue order."""
    published = 0
    for item in queue:
        request = item if isinstance(item, ProvisionRequest) else parse_request(item)
        bus.publish(PROVISION_REQUESTED, request)
        published += 1
    return published
