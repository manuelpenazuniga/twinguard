from vmprov.formatting import format_summary
from vmprov.models import Decision, PolicyServiceTimeout, ProvisionRequest
from vmprov.pipeline import process_queue


class FakePolicy:
    def __init__(self, answers):
        self.answers = answers
        self.asked = []

    def decide(self, request):
        self.asked.append(request.request_id)
        answer = self.answers[request.request_id]
        if answer == "timeout":
            raise PolicyServiceTimeout("quota policy service did not answer")
        return answer


class FakeCompute:
    def __init__(self):
        self.created = []

    def create_instance(self, request_id, project, region, machine_type, count):
        self.created.append(request_id)
        return [f"i-{request_id}-{n}" for n in range(count)]


def req(request_id, region="us-east-1", vcpus=8, count=1):
    return ProvisionRequest(request_id, "proj-a", region, "n2-standard-8", vcpus, count)


def test_unrestricted_region_skips_policy_and_provisions():
    policy, compute = FakePolicy({}), FakeCompute()
    summary = process_queue([req("r1", count=2)], policy, compute)
    assert compute.created == ["r1"]
    assert policy.asked == []
    assert summary.instances["r1"] == ["i-r1-0", "i-r1-1"]


def test_restricted_region_follows_policy_decision():
    policy = FakePolicy({"a": Decision.ALLOW, "d": Decision.DENY, "h": Decision.HOLD})
    compute = FakeCompute()
    queue = [req("a", "eu-sovereign-1"), req("d", "eu-sovereign-1"), req("h", "us-gov-east-1")]
    summary = process_queue(queue, policy, compute)
    assert compute.created == ["a"]
    assert summary.denied == ["d"]
    assert summary.held == ["h"]


def test_raw_queue_messages_are_parsed():
    compute = FakeCompute()
    raw = {"request_id": "m1", "project": "p", "region": "us-east-1",
           "machine_type": "e2-small", "vcpus": "2"}
    summary = process_queue([raw], FakePolicy({}), compute)
    assert summary.provisioned == ["m1"]


def test_run_finishes_when_policy_service_times_out():
    policy = FakePolicy({"slow": "timeout", "ok": Decision.ALLOW})
    compute = FakeCompute()
    queue = [req("slow", "ap-restricted-2", vcpus=32), req("ok", "eu-sovereign-1"),
             req("plain")]
    summary = process_queue(queue, policy, compute)
    assert summary.processed == 3
    assert "ok" in compute.created and "plain" in compute.created


def test_format_summary():
    policy = FakePolicy({"d": Decision.DENY})
    summary = process_queue([req("x"), req("d", "eu-sovereign-1")], policy, FakeCompute())
    text = format_summary(summary)
    assert text.splitlines()[0] == "processed 2 requests, created 1 instance"
    assert "denied:      d" in text
