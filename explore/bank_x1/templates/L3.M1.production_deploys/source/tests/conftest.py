import pytest

from deploys.policy import Decision, PolicyTimeout


class FakePolicy:
    def __init__(self, decisions=None, slow=()):
        self.decisions = decisions or {}
        self.slow = set(slow)
        self.calls = []

    def evaluate(self, request, timeout):
        self.calls.append((request.request_id, timeout))
        if request.request_id in self.slow:
            raise PolicyTimeout(f"policy service timed out after {timeout}s")
        return self.decisions.get(request.request_id, Decision.ALLOW)


class FakeRunner:
    def __init__(self):
        self.deployed = []

    def deploy(self, request):
        self.deployed.append(request.request_id)
        return f"dpl-{len(self.deployed)}"


@pytest.fixture
def runner():
    return FakeRunner()


@pytest.fixture
def make_policy():
    return FakePolicy
