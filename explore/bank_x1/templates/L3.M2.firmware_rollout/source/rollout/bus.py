"""In-process event bus that wires the rollout handlers together.

Delivery is synchronous and in subscription order. Handler exceptions are not
swallowed: they propagate to whoever published the event.
"""
from collections import defaultdict

PUSH_REQUESTED = "firmware.push.requested"
ROLLBACK_REQUESTED = "firmware.rollback.requested"
PUSH_COMPLETED = "firmware.push.completed"
ROLLBACK_COMPLETED = "firmware.rollback.completed"
REQUEST_REJECTED = "firmware.request.rejected"


class EventBus:
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
