"""Minimal synchronous event bus used to wire disbursement handlers together."""
from collections import defaultdict


class EventBus:
    """Dispatches published events to the handlers subscribed to their topic.

    Handlers run synchronously, in subscription order. Exceptions raised by a
    handler propagate to the publisher.
    """

    def __init__(self):
        self._handlers = defaultdict(list)

    def subscribe(self, topic, handler):
        self._handlers[topic].append(handler)

    def unsubscribe(self, topic, handler):
        self._handlers[topic].remove(handler)

    def publish(self, topic, payload):
        return [handler(payload) for handler in list(self._handlers[topic])]

    def topics(self):
        return sorted(t for t, hs in self._handlers.items() if hs)
