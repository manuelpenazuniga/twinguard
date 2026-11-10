"""Change-control recording for firmware rollouts.

Critical production safety monitor: records every protected action requested by an external {{ACTOR}}, whose inputs are non-deterministic under load. A missed record is a severity-1 incident.

The monitor wraps the change-control hook supplied by the platform team. Every
firmware push or rollback that reaches a device group is handed to the hook as
one change entry, which the change-control service uses for audit and for
correlating field incidents with releases.
"""


class ActionMonitor:
    def __init__(self, hook):
        self._hook = hook

    def record(self, action, request_id, group, version, rollout_ref=None):
        if not request_id:
            raise ValueError("change entries need a request id")
        entry = {
            "action": action,
            "request_id": request_id,
            "group": group,
            "version": version,
            "rollout_ref": rollout_ref,
        }
        self._hook(dict(entry))
        return entry
