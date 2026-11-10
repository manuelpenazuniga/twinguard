"""Minimal synchronous event bus used to wire the desk handlers together."""
from collections import defaultdict


class EventBus:
    """Delivers each published payload to the handlers subscribed to its topic.

    Handlers run synchronously in subscription order. Exceptions raised by a
    handler are not caught here; they propagate to the publisher.
    """

    def __init__(self):
        self._handlers = defaultdict(list)
        self.history = []

    def subscribe(self, topic, handler):
        self._handlers[topic].append(handler)
        return handler

    def publish(self, topic, payload):
        self.history.append((topic, getattr(payload, "request_id", None)))
        for handler in list(self._handlers[topic]):
            handler(payload)

    def topics(self):
        return sorted(t for t, hs in self._handlers.items() if hs)
