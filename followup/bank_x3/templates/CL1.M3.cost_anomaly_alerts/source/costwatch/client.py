"""Provisioning client that drains the resource request queue."""
from collections import deque

from costwatch.models import Outcome


class ManagedClient:
    """Submits queued resource requests through the spend guard to the provisioner."""

    def __init__(self, guard, provisioner):
        self._guard = guard
        self._provisioner = provisioner
        self.history = []

    def submit(self, request):
        decision = self._guard.review(request)
        if not decision.allowed:
            outcome = Outcome(request.request_id, False, "over budget envelope")
        else:
            self._provisioner.provision(request)
            outcome = Outcome(request.request_id, True, "provisioned")
        self.history.append(outcome)
        return outcome

    def run(self, requests):
        queue = deque(requests)
        outcomes = []
        while queue:
            outcomes.append(self.submit(queue.popleft()))
        return outcomes

    def provisioned_ids(self):
        return [o.request_id for o in self.history if o.provisioned]
