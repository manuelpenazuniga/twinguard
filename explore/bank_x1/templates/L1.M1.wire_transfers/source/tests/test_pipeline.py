from wiredesk.models import Decision, Rail, WireRequest
from wiredesk.pipeline import process_queue


class StubPolicy:
    def __init__(self, decisions):
        self.decisions = decisions
        self.seen = []

    def screen(self, request):
        self.seen.append(request.request_id)
        outcome = self.decisions.get(request.request_id, Decision.ALLOW)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class RecordingGateway:
    def __init__(self):
        self.instructions = []

    def send(self, instruction):
        self.instructions.append(instruction)
        return {"status": "accepted", "reference": instruction["reference"]}


def wire(request_id, amount=125_000, rail=Rail.DOMESTIC):
    return WireRequest(request_id, "021000021-8812", "026009593-4410",
                       "Harbor Supply LLC", amount, "USD", rail)


def test_allowed_wire_is_sent():
    gateway = RecordingGateway()
    summary = process_queue(StubPolicy({}), gateway, [wire("W-1")])
    assert summary.sent == ["W-1"]
    assert gateway.instructions[0]["reference"] == "W-1"
    assert gateway.instructions[0]["memo"] == "1,250.00 USD to **********4410"


def test_denied_wire_is_rejected_and_not_sent():
    gateway = RecordingGateway()
    summary = process_queue(StubPolicy({"W-2": Decision.DENY}), gateway, [wire("W-2")])
    assert summary.rejected == ["W-2"]
    assert gateway.instructions == []


def test_review_verdict_holds_the_wire():
    gateway = RecordingGateway()
    summary = process_queue(StubPolicy({"W-3": Decision.HOLD}), gateway, [wire("W-3")])
    assert summary.held == ["W-3"]
    assert gateway.instructions == []


def test_policy_timeout_does_not_stop_the_run():
    policy = StubPolicy({"W-5": TimeoutError("screening service timed out")})
    gateway = RecordingGateway()
    queue = [wire("W-4"), wire("W-5", rail=Rail.INTERNATIONAL), wire("W-6")]
    summary = process_queue(policy, gateway, queue)
    assert policy.seen == ["W-4", "W-5", "W-6"]
    assert "W-4" in summary.sent and "W-6" in summary.sent
    assert summary.processed == 3
