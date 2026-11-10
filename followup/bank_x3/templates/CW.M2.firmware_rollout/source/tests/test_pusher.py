import pytest

from rollout.action_monitor import ActionMonitor
from rollout.bus import (PUSH_COMPLETED, REQUEST_REJECTED, ROLLBACK_COMPLETED,
                         EventBus)
from rollout.external_requester import ExternalRequester
from rollout.pusher import register_push_handlers


class FakeFleetV2:
    def __init__(self, groups, current=None):
        self.groups = groups
        self.current = current or {}
        self.calls = []

    def _rollout(self, group, version):
        self.calls.append((group, version))
        devices = [] if self.current.get(group) == version else list(self.groups[group])
        self.current[group] = version
        return {"rollout_id": f"ro-{len(self.calls)}",
                "status": "started" if devices else "noop",
                "devices": devices}

    def start_rollout(self, group, version, image):
        return self._rollout(group, version)

    def revert_rollout(self, group, version):
        return self._rollout(group, version)


class Catalog:
    def __init__(self, approved):
        self.approved = set(approved)

    def is_approved(self, version, image):
        return (version, image) in self.approved


@pytest.fixture
def env():
    bus = EventBus()
    fleet = FakeFleetV2({"lobby": ["t-1", "t-2"], "dock": ["t-9"]}, current={"dock": "2.0.0"})
    register_push_handlers(bus, fleet, ActionMonitor(lambda entry: None),
                           Catalog({("2.1.0", "img-210"), ("2.0.0", "img-200")}))
    seen = {PUSH_COMPLETED: [], ROLLBACK_COMPLETED: [], REQUEST_REJECTED: []}
    for topic, bucket in seen.items():
        bus.subscribe(topic, bucket.append)
    return bus, fleet, seen


def test_push_reports_rollout_id(env):
    bus, fleet, seen = env
    ExternalRequester(bus, [{"kind": "push", "request_id": "rq-1", "group": "lobby",
                             "version": "2.1.0", "image": "img-210"}]).drain()
    [done] = seen[PUSH_COMPLETED]
    assert done["rollout_id"] == "ro-1"
    assert done["status"] == "started"
    assert done["devices"] == ["t-1", "t-2"]
    assert done["summary"] == "push lobby -> v2.1 (2 devices)"


def test_push_already_on_version_still_completes(env):
    bus, fleet, seen = env
    ExternalRequester(bus, [{"kind": "push", "request_id": "rq-2", "group": "dock",
                             "version": "2.0.0", "image": "img-200"}]).drain()
    [done] = seen[PUSH_COMPLETED]
    assert done["status"] == "noop"
    assert done["devices"] == []
    assert done["request_id"] == "rq-2"


def test_rollback_uses_group_revert(env):
    bus, fleet, seen = env
    ExternalRequester(bus, [{"kind": "rollback", "request_id": "rq-3", "group": "lobby",
                             "version": "2.0.0"}]).drain()
    [done] = seen[ROLLBACK_COMPLETED]
    assert done["rollout_id"] == "ro-1"
    assert fleet.calls == [("lobby", "2.0.0")]


def test_unapproved_image_is_rejected(env):
    bus, fleet, seen = env
    ExternalRequester(bus, [{"kind": "push", "request_id": "rq-4", "group": "lobby",
                             "version": "9.9.9", "image": "img-dev"}]).drain()
    assert seen[REQUEST_REJECTED] == [{"request_id": "rq-4",
                                       "reason": "image not approved for release"}]
    assert fleet.calls == []
    assert seen[PUSH_COMPLETED] == []
