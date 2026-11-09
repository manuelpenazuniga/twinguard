import pytest

from setpoints import SetpointChange


class StubTransport:
    """Answers policy requests from a table keyed by change id."""

    def __init__(self, answers):
        self.answers = answers
        self.requests = []

    def post(self, path, payload, timeout):
        self.requests.append((path, payload["change_id"]))
        answer = self.answers[payload["change_id"]]
        if answer == "timeout":
            raise TimeoutError("read timed out")
        return {"change_id": payload["change_id"], "decision": answer}


class StubBmsClient:
    def __init__(self):
        self.writes = []

    def write_property(self, point, value):
        self.writes.append((point, value))


def make_change(change_id, target_c=22.0, current_c=21.0, mode="heat", zone="z1"):
    return SetpointChange(change_id, "hq", zone, mode, current_c, target_c)


@pytest.fixture
def bms():
    return StubBmsClient()
