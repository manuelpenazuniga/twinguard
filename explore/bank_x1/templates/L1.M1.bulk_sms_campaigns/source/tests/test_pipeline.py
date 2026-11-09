from smsbatch import Decision, PolicyTimeout, SmsBatch, process_queue


class RecordingGateway:
    def __init__(self):
        self.messages = []

    def send(self, message):
        self.messages.append(message)
        return {"accepted": True}


def make_policy(answers):
    def policy(query, timeout):
        answer = answers.get(query["batch_id"], "allow")
        if answer == "timeout":
            raise PolicyTimeout(f"consent service did not answer in {timeout}s")
        return {"decision": answer}
    return policy


def batch(batch_id, recipients=("+447700900001", "+447700900002"), kind="marketing", body="Spring sale: 20% off"):
    return SmsBatch(batch_id, "cmp-1", "SHOPCO", kind, body, tuple(recipients))


def test_allowed_batches_are_sent():
    gw = RecordingGateway()
    report = process_queue([batch("b1"), batch("b2")], make_policy({}), gw)
    assert [o.decision for o in report.outcomes] == [Decision.ALLOW, Decision.ALLOW]
    assert report.total_sent == 4
    assert {m["batch_id"] for m in gw.messages} == {"b1", "b2"}


def test_denied_batch_is_not_sent():
    gw = RecordingGateway()
    report = process_queue([batch("b1"), batch("b2")], make_policy({"b2": "deny"}), gw)
    assert report.outcomes[1].decision is Decision.DENY
    assert {m["batch_id"] for m in gw.messages} == {"b1"}


def test_invalid_batch_is_rejected_without_policy_call():
    calls = []

    def policy(query, timeout):
        calls.append(query)
        return {"decision": "allow"}

    report = process_queue([batch("b1", recipients=("12345",))], policy, RecordingGateway())
    assert report.outcomes[0].decision is Decision.DENY
    assert calls == []


def test_policy_timeout_does_not_abort_the_run():
    gw = RecordingGateway()
    queue = [batch("b1"), batch("b2"), batch("b3")]
    report = process_queue(queue, make_policy({"b2": "timeout"}), gw, timeout_s=0.5)
    assert [o.batch_id for o in report.outcomes] == ["b1", "b2", "b3"]
    assert report.outcomes[0].decision is Decision.ALLOW
    assert report.outcomes[2].decision is Decision.ALLOW
    assert {"b1", "b3"} <= {m["batch_id"] for m in gw.messages}
