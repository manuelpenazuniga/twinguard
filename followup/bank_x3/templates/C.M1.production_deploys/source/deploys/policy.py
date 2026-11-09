"""Deploy request model and the change policy service contract."""
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

KINDS = ("release", "hotfix", "rollback")


class Decision(Enum):
    ALLOW = "allow"
    DENY = "deny"
    HOLD = "hold"


class PolicyTimeout(TimeoutError):
    """The change policy service did not answer within the configured timeout."""


@dataclass(frozen=True)
class DeployRequest:
    request_id: str
    service: str
    version: str
    kind: str = "release"

    def __post_init__(self):
        if self.kind not in KINDS:
            raise ValueError(f"unknown deploy kind: {self.kind}")


class PolicyService(Protocol):
    def evaluate(self, request: DeployRequest, timeout: float) -> Decision: ...


class DeployRunner(Protocol):
    def deploy(self, request: DeployRequest) -> str: ...
