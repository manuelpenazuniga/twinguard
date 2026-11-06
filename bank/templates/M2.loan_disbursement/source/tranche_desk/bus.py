"""In-process event bus used to wire the tranche desk handlers together."""
from collections import defaultdict

TRANCHE_REQUESTED = "tranche.requested"
TRANCHE_REJECTED = "tranche.rejected"
TRANCHE_DISBURSED = "tranche.disbursed"


class EventBus:
    """Synchronous publish/subscribe bus.

    Handlers run in subscription order on the publisher's thread. Exceptions
    raised by a handler propagate to the publisher so the request queue can
    decide whether to retry.
    """

    def __init__(self):
        self._handlers = defaultdict(list)
        self.history = []

    def subscribe(self, topic, handler):
        self._handlers[topic].append(handler)
        return handler

    def unsubscribe(self, topic, handler):
        self._handlers[topic].remove(handler)

    def publish(self, topic, payload):
        self.history.append((topic, payload))
        for handler in list(self._handlers[topic]):
            handler(payload)

    def events(self, topic):
        return [payload for name, payload in self.history if name == topic]
