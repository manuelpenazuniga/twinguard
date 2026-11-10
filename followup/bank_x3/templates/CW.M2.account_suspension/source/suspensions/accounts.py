"""Clients for the accounts backend.

``LegacyAccountClient`` wraps the original status endpoint and is being
decommissioned. ``AccountsGateway`` replaces it: status changes are submitted
as ``StatusChange`` objects and acknowledged with a ``ChangeReceipt``. Both
keep account state in memory here; the service wiring swaps in the HTTP
transports.
"""
from dataclasses import dataclass
from itertools import count

from .models import AccountState


class UnknownAccount(LookupError):
    """Raised when an account id is not known to the backend."""


@dataclass(frozen=True)
class StatusChange:
    account_id: str
    target_state: AccountState
    reason: str
    idempotency_key: str


@dataclass(frozen=True)
class ChangeReceipt:
    change_id: str
    account_id: str
    state: AccountState
    applied: bool


class AccountsGateway:
    """Accounts platform v2 client."""

    def __init__(self, accounts=None, prefix="chg"):
        self._accounts = {k: AccountState(v) for k, v in (accounts or {}).items()}
        self._receipts = {}
        self._seq = count(1)
        self._prefix = prefix

    def state_of(self, account_id):
        try:
            return self._accounts[account_id]
        except KeyError:
            raise UnknownAccount(account_id) from None

    def submit(self, change):
        """Apply ``change``; replays of the same idempotency key return the first receipt."""
        if change.idempotency_key in self._receipts:
            return self._receipts[change.idempotency_key]
        current = self.state_of(change.account_id)
        target = AccountState(change.target_state)
        self._accounts[change.account_id] = target
        receipt = ChangeReceipt(
            change_id=f"{self._prefix}-{next(self._seq):05d}",
            account_id=change.account_id,
            state=target,
            applied=current is not target,
        )
        self._receipts[change.idempotency_key] = receipt
        return receipt


class LegacyAccountClient:
    """Deprecated status endpoint; use ``AccountsGateway.submit`` instead."""

    def __init__(self, accounts=None):
        self._accounts = {k: AccountState(v) for k, v in (accounts or {}).items()}

    def state_of(self, account_id):
        try:
            return self._accounts[account_id]
        except KeyError:
            raise UnknownAccount(account_id) from None

    def set_account_status(self, account_id, status, reason):
        """Set the status; returns True when the stored status actually changed."""
        current = self.state_of(account_id)
        self._accounts[account_id] = AccountState(status)
        return current is not AccountState(status)
