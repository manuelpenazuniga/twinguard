"""Data types shared by the provisioning pipeline."""
from __future__ import annotations

import enum
from dataclasses import dataclass, field


class Decision(enum.Enum):
    """Outcome of a quota policy decision for one request."""

    ALLOW = "allow"
    DENY = "deny"
    HOLD = "hold"  # parked; the scheduler re-queues held requests at the next quota window


class PolicyServiceTimeout(TimeoutError):
    """Raised by a quota policy client when the service does not answer in time."""


class ProvisioningError(RuntimeError):
    """Raised when a queued request cannot be processed."""


@dataclass(frozen=True)
class ProvisionRequest:
    request_id: str
    project: str
    region: str
    machine_type: str
    vcpus: int
    count: int = 1


@dataclass
class RunSummary:
    provisioned: list[str] = field(default_factory=list)
    denied: list[str] = field(default_factory=list)
    held: list[str] = field(default_factory=list)
    instances: dict[str, list[str]] = field(default_factory=dict)

    @property
    def processed(self) -> int:
        return len(self.provisioned) + len(self.denied) + len(self.held)
