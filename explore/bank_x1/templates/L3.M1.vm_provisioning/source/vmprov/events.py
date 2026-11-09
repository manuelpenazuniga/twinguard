"""Minimal in-process event bus used to wire the pipeline stages together."""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable

PROVISION_REQUESTED = "provision.requested"
PROVISION_APPROVED = "provision.approved"
PROVISION_DENIED = "provision.denied"
PROVISION_HELD = "provision.held"

Handler = Callable[[Any], None]


class EventBus:
    """Synchronous publish/subscribe bus; handlers run in subscription order."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[Handler]] = defaultdict(list)

    def subscribe(self, topic: str, handler: Handler) -> None:
        self._handlers[topic].append(handler)

    def publish(self, topic: str, payload: Any) -> None:
        for handler in list(self._handlers.get(topic, ())):
            handler(payload)

    def topics(self) -> list[str]:
        return sorted(t for t, hs in self._handlers.items() if hs)
