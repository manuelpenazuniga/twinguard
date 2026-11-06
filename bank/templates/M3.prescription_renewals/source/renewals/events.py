"""Minimal synchronous event bus used to wire the renewal pipeline together."""

from collections import defaultdict
from typing import Any, Callable

Handler = Callable[..., Any]


class EventBus:
    """Dispatches named events to the handlers registered for them, in order."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[Handler]] = defaultdict(list)

    def subscribe(self, topic: str, handler: Handler) -> None:
        """Register ``handler`` to be called for every event published on ``topic``."""
        self._handlers[topic].append(handler)

    def unsubscribe(self, topic: str, handler: Handler) -> None:
        if handler in self._handlers.get(topic, []):
            self._handlers[topic].remove(handler)

    def handlers(self, topic: str) -> list[Handler]:
        return list(self._handlers.get(topic, []))

    def publish(self, topic: str, **payload: Any) -> int:
        """Call each handler with the payload; returns how many handlers ran."""
        count = 0
        for handler in self.handlers(topic):
            handler(**payload)
            count += 1
        return count
