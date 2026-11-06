from setpoints import ActionAuditor, ActionRequester, EnergyPolicyClient, SetpointChange


class FakeTransport:
    def __init__(self, decisions=None, slow=()):
        self.decisions = dict(decisions or {})
        self.slow = set(slow)
        self.calls = []

    def post(self, path, payload, timeout_s):
        self.calls.append(payload["request_id"])
        if payload["request_id"] in self.slow:
            raise TimeoutError("read timed out")
        return {"decision": self.decisions.get(payload["request_id"], "allow")}


class RecordingController:
    def __init__(self):
        self.applied = []

    def apply_setpoint(self, building, zone, target_c, mode):
        self.applied.append((building, zone, target_c, mode))


def change(request_id, zone="z1", target_c=22.0, mode="cool"):
    return SetpointChange(request_id, "hq", zone, target_c, mode)


def build(decisions=None, slow=()):
    transport = FakeTransport(decisions, slow)
    controller = RecordingController()
    auditor = ActionAuditor(EnergyPolicyClient(transport, timeout_s=0.5))
    return ActionRequester(auditor, controller), transport, controller
