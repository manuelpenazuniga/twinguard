"""Pre-flight policy checks for queued enforcement requests."""
from .models import Action


class PolicyViolation(Exception):
    """The request may not be applied from the queue."""


class SuspensionPolicy:
    """Rules every queued request must satisfy before it reaches the backend."""

    def __init__(self, protected_accounts=(), min_reason_length=8):
        self._protected = frozenset(protected_accounts)
        self._min_reason_length = min_reason_length

    def check(self, request):
        if request.action is Action.SUSPEND and request.account_id in self._protected:
            raise PolicyViolation(
                f"{request.account_id} is on the protected list; escalate to a trust lead"
            )
        if len(request.reason.strip()) < self._min_reason_length:
            raise PolicyViolation(f"{request.request_id}: reason is too short")
