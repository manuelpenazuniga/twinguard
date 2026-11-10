"""Minimal synchronous event bus used to wire the deploy handlers together."""
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable

Handler = Callable[["Event"], None]


@dataclass(frozen=True)
class Event:
    topic: str
    payload: Any
    meta: dict = field(default_factory=dict)


class EventBus:
    def __init__(self):
        self._handlers: dict[str, list[Handler]] = defaultdict(list)
        self.published: list[str] = []

    def subscribe(self, topic: str, handler: Handler) -> None:
        self._handlers[topic].append(handler)

    def publish(self, topic: str, payload: Any, **meta) -> None:
        self.published.append(topic)
        event = Event(topic, payload, dict(meta))
        for handler in list(self._handlers[topic]):
            handler(event)
