"""In-process event bus used to wire the broadcast pipeline together.

Handlers are called synchronously, in registration order. Exceptions raised by a
handler propagate to the publisher so that a failing stage is never silently skipped.
"""
from collections import defaultdict

JOB_SUBMITTED = "broadcast.submitted"
JOB_DELIVERED = "broadcast.delivered"
MONITOR_REPORT = "monitor.report"


class EventBus:
    """Minimal synchronous publish/subscribe bus."""

    def __init__(self):
        self._handlers = defaultdict(list)
        self.history = []

    def subscribe(self, topic, handler):
        self._handlers[topic].append(handler)
        return handler

    def unsubscribe(self, topic, handler):
        if handler in self._handlers[topic]:
            self._handlers[topic].remove(handler)

    def handlers(self, topic):
        return list(self._handlers[topic])

    def publish(self, topic, payload):
        self.history.append(topic)
        for handler in self.handlers(topic):
            handler(payload)
