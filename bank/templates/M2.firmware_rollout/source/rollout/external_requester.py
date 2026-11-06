"""Queue consumer that turns rollout requests into bus events."""
from collections import deque

from .bus import PUSH_REQUESTED, ROLLBACK_REQUESTED

_TOPICS = {"push": PUSH_REQUESTED, "rollback": ROLLBACK_REQUESTED}


class ExternalRequester:
    """Drains queued rollout requests and publishes one event per request."""

    def __init__(self, bus, queue=None):
        self._bus = bus
        self._queue = deque(queue or ())

    def enqueue(self, request):
        self._queue.append(dict(request))

    def pending(self):
        return len(self._queue)

    def drain(self):
        handled = 0
        while self._queue:
            request = self._queue.popleft()
            topic = _TOPICS.get(request.get("kind"))
            if topic is None:
                raise ValueError(f"unknown request kind: {request.get('kind')!r}")
            self._bus.publish(topic, request)
            handled += 1
        return handled
