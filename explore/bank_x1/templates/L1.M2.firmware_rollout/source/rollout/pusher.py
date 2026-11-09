"""Firmware push and rollback handlers for device groups.

The handlers are registered on the event bus and talk to the fleet through an
injected transport client.
"""
from .bus import (PUSH_COMPLETED, PUSH_REQUESTED, REQUEST_REJECTED,
                  ROLLBACK_COMPLETED, ROLLBACK_REQUESTED)
from .formatting import summarize
from .validation import RejectedRequest, check_request


def register_push_handlers(bus, transport, monitor, catalog):
    """Subscribe the push and rollback handlers on ``bus``."""

    def admitted(request):
        try:
            check_request(request, catalog)
        except RejectedRequest as exc:
            bus.publish(REQUEST_REJECTED, {"request_id": exc.request_id, "reason": exc.reason})
            return False
        return True

    def on_push_requested(request):
        if admitted(request):
            push_firmware(request, transport, monitor, bus)

    def on_rollback_requested(request):
        if admitted(request):
            rollback_firmware(request, transport, monitor, bus)

    bus.subscribe(PUSH_REQUESTED, on_push_requested)
    bus.subscribe(ROLLBACK_REQUESTED, on_rollback_requested)
    return on_push_requested, on_rollback_requested


def push_firmware(request, transport, monitor, bus):
    group, version = request["group"], request["version"]
    delivered = []
    for device_id in transport.group_members(group):
        if transport.send_image(device_id, request["image"], version):
            delivered.append(device_id)
    monitor.record("push", request["request_id"], group, version)
    result = {
        "request_id": request["request_id"],
        "group": group,
        "version": version,
        "devices": delivered,
        "summary": summarize("push", group, version, len(delivered)),
    }
    bus.publish(PUSH_COMPLETED, result)
    return result


def rollback_firmware(request, transport, monitor, bus):
    group, version = request["group"], request["version"]
    reverted = []
    for device_id in transport.group_members(group):
        if transport.send_rollback(device_id, version):
            reverted.append(device_id)
    monitor.record("rollback", request["request_id"], group, version)
    result = {
        "request_id": request["request_id"],
        "group": group,
        "version": version,
        "devices": reverted,
        "summary": summarize("rollback", group, version, len(reverted)),
    }
    bus.publish(ROLLBACK_COMPLETED, result)
    return result
