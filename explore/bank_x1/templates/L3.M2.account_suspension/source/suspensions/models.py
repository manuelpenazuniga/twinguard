"""Request and outcome types for the account enforcement queue."""
from dataclasses import dataclass
from enum import Enum


class Action(str, Enum):
    SUSPEND = "suspend"
    REINSTATE = "reinstate"


class AccountState(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


class OutcomeStatus(str, Enum):
    APPLIED = "applied"
    UNCHANGED = "unchanged"
    REJECTED = "rejected"


@dataclass(frozen=True)
class SuspensionRequest:
    """One entry of the moderation request queue."""

    request_id: str
    account_id: str
    action: Action
    reason: str
    case_ref: str = ""

    @property
    def target_state(self) -> AccountState:
        if self.action is Action.SUSPEND:
            return AccountState.SUSPENDED
        return AccountState.ACTIVE


@dataclass(frozen=True)
class Outcome:
    """Result reported back to the queue for one request."""

    request_id: str
    account_id: str
    status: OutcomeStatus
    notice: str = ""
    change_id: str | None = None
