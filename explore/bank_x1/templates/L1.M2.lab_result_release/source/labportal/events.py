"""Minimal synchronous event bus used to wire the release pipeline together."""
from collections import defaultdict

RELEASE_REQUESTED = "release.requested"
RELEASE_COMPLETED = "release.completed"
RELEASE_HELD = "release.held"


class EventBus:
    """Delivers each published payload to the handlers subscribed to its topic, in order."""

    def __init__(self):
        self._handlers = defaultdict(list)

    def subscribe(self, topic, handler):
        self._handlers[topic].append(handler)
        return handler

    def unsubscribe(self, topic, handler):
        if handler in self._handlers[topic]:
            self._handlers[topic].remove(handler)

    def publish(self, topic, payload):
        delivered = 0
        for handler in list(self._handlers[topic]):
            handler(payload)
            delivered += 1
        return delivered
