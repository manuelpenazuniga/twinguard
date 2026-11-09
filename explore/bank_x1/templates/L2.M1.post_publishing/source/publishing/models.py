"""Data types shared by the publish-queue pipeline."""
from __future__ import annotations

import enum
from dataclasses import dataclass, field


class Decision(enum.Enum):
    """Outcome of the moderation gate for one publish request."""

    ALLOW = "allow"
    DENY = "deny"
    HOLD = "hold"


class PolicyTimeout(TimeoutError):
    """The moderation policy service did not answer within the configured timeout."""


@dataclass(frozen=True)
class PublishRequest:
    post_id: str
    author_id: str
    body: str
    flags: tuple[str, ...] = ()
    author_trusted: bool = False
    channel: str = "feed"


@dataclass
class RunResult:
    published: list[str] = field(default_factory=list)
    held: list[str] = field(default_factory=list)
    denied: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.published) + len(self.held) + len(self.denied)
