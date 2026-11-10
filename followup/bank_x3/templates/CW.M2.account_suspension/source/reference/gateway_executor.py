"""Reference usage of the accounts platform v2 API (``AccountsGateway``).

Provided by the accounts platform team as the migration example for status
writers that still call ``LegacyAccountClient.set_account_status``.
"""
from suspensions.accounts import StatusChange
from suspensions.models import AccountState, Outcome, OutcomeStatus
from suspensions.notices import render_notice


class GatewayStatusWriter:
    def __init__(self, gateway):
        self._gateway = gateway

    def suspend_account(self, request):
        receipt = self._gateway.submit(self._change(request, AccountState.SUSPENDED))
        return self._outcome(request, receipt)

    def reinstate_account(self, request):
        receipt = self._gateway.submit(self._change(request, AccountState.ACTIVE))
        return self._outcome(request, receipt)

    @staticmethod
    def _change(request, state):
        # The request id doubles as the idempotency key, so queue redeliveries
        # are acknowledged with the original receipt instead of a second write.
        return StatusChange(
            account_id=request.account_id,
            target_state=state,
            reason=request.reason,
            idempotency_key=request.request_id,
        )

    @staticmethod
    def _outcome(request, receipt):
        status = OutcomeStatus.APPLIED if receipt.applied else OutcomeStatus.UNCHANGED
        return Outcome(request.request_id, request.account_id, status,
                       notice=render_notice(request, status),
                       change_id=receipt.change_id)
