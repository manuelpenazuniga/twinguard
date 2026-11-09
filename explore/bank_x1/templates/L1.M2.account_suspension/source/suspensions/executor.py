"""Applies queued suspension and reinstatement requests to the accounts backend."""
from .models import AccountState, Action, Outcome, OutcomeStatus
from .notices import render_notice
from .policy import PolicyViolation


class MonitoredExecutor:
    """Works through the moderation request queue one request at a time.

    The accounts client, the policy and the audit monitor are injected so the
    service wiring decides which backends are used.
    """

    def __init__(self, accounts, policy, monitor):
        self._accounts = accounts
        self._policy = policy
        self._monitor = monitor

    def run(self, queue):
        """Process every request of ``queue`` in order."""
        return [self.process(request) for request in queue]

    def process(self, request):
        try:
            self._policy.check(request)
        except PolicyViolation as exc:
            return Outcome(request.request_id, request.account_id,
                           OutcomeStatus.REJECTED, notice=str(exc))
        if request.action is Action.SUSPEND:
            return self.suspend_account(request)
        return self.reinstate_account(request)

    def suspend_account(self, request):
        changed = self._accounts.set_account_status(
            request.account_id, AccountState.SUSPENDED.value, request.reason)
        self._monitor.record_action(request.request_id, Action.SUSPEND, request.account_id)
        return self._outcome(request, changed)

    def reinstate_account(self, request):
        changed = self._accounts.set_account_status(
            request.account_id, AccountState.ACTIVE.value, request.reason)
        self._monitor.record_action(request.request_id, Action.REINSTATE, request.account_id)
        return self._outcome(request, changed)

    def _outcome(self, request, changed):
        status = OutcomeStatus.APPLIED if changed else OutcomeStatus.UNCHANGED
        return Outcome(request.request_id, request.account_id, status,
                       notice=render_notice(request, status))
