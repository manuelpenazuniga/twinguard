"""Minimal synchronous event bus used to wire the declaration pipeline together.

Handlers run in subscription order, in the publisher's call stack. Exceptions raised by a
handler propagate to the publisher so that a failed filing is never silently dropped.
"""
from collections import defaultdict


class EventBus:
    """Topic-based publish/subscribe registry."""

    def __init__(self):
        self._handlers = defaultdict(list)
        self.published = []

    def subscribe(self, topic, handler):
        """Register ``handler(payload)`` for ``topic`` and return it."""
        self._handlers[topic].append(handler)
        return handler

    def unsubscribe(self, topic, handler):
        if handler in self._handlers[topic]:
            self._handlers[topic].remove(handler)

    def publish(self, topic, payload):
        """Deliver ``payload`` to every handler subscribed to ``topic``."""
        self.published.append(topic)
        for handler in list(self._handlers[topic]):
            handler(payload)
        return len(self._handlers[topic])
