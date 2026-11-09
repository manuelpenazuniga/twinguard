"""Minimal synchronous event bus used by the moderation queue worker.

Handlers are plain callables registered per event name. A handler registered
under ``"*"`` receives every event after the specific handlers have run.
"""
from collections import defaultdict
from dataclasses import dataclass, field

WILDCARD = "*"


@dataclass(frozen=True)
class Event:
    name: str
    payload: dict = field(default_factory=dict)


class EventBus:
    def __init__(self):
        self._handlers = defaultdict(list)

    def subscribe(self, name, handler):
        self._handlers[name].append(handler)
        return handler

    def unsubscribe(self, name, handler):
        if handler in self._handlers[name]:
            self._handlers[name].remove(handler)

    def handlers(self, name):
        return tuple(self._handlers[name])

    def publish(self, name, payload=None):
        event = Event(name, dict(payload or {}))
        for handler in list(self._handlers[name]) + list(self._handlers[WILDCARD]):
            handler(event)
        return event
