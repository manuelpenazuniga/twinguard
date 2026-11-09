"""Fleet API v2 example handlers, maintained by the device platform team.

v2 fans a rollout out to a whole device group server side. ``start_rollout``
and ``revert_rollout`` return a dict with ``rollout_id``, ``status``
(``"started"`` or ``"noop"`` when the group is already on that version) and the
list of ``devices`` the rollout touched. A ``noop`` rollout is still a
completed rollout and is reported as such.
"""
from rollout.bus import PUSH_COMPLETED, ROLLBACK_COMPLETED
from rollout.formatting import summarize


def push_firmware(request, transport, bus):
    group, version = request["group"], request["version"]
    rollout = transport.start_rollout(group, version, request["image"])
    result = {
        "request_id": request["request_id"],
        "rollout_id": rollout["rollout_id"],
        "status": rollout["status"],
        "group": group,
        "version": version,
        "devices": list(rollout["devices"]),
        "summary": summarize("push", group, version, len(rollout["devices"])),
    }
    bus.publish(PUSH_COMPLETED, result)
    return result


def rollback_firmware(request, transport, bus):
    group, version = request["group"], request["version"]
    rollout = transport.revert_rollout(group, version)
    result = {
        "request_id": request["request_id"],
        "rollout_id": rollout["rollout_id"],
        "status": rollout["status"],
        "group": group,
        "version": version,
        "devices": list(rollout["devices"]),
        "summary": summarize("rollback", group, version, len(rollout["devices"])),
    }
    bus.publish(ROLLBACK_COMPLETED, result)
    return result
