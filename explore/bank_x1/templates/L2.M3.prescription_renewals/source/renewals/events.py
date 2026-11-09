"""Minimal synchronous event bus used to wire the renewal pipeline together.

Handlers run in subscription order. Exceptions raised by a handler propagate to
the publisher so that a failing step never goes unnoticed.
"""
from collections import defaultdict


class EventBus:
    """Topic based publish/subscribe with synchronous delivery."""

    def __init__(self):
        self._handlers = defaultdict(list)
        self.published = []

    def subscribe(self, topic, handler):
        self._handlers[topic].append(handler)
        return handler

    def unsubscribe(self, topic, handler):
        if handler in self._handlers[topic]:
            self._handlers[topic].remove(handler)

    def handlers_for(self, topic):
        return tuple(self._handlers[topic])

    def publish(self, topic, payload):
        self.published.append(topic)
        for handler in list(self._handlers[topic]):
            handler(payload)
