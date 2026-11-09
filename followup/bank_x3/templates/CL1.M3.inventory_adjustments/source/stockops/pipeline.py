"""Event bus and wiring for the stock adjustment pipeline."""
from collections import defaultdict

from .control_monitor import register_control_monitor
from .upstream_worker import REQUESTED, register_upstream_worker


class EventBus:
    """Synchronous publish/subscribe bus; handlers run in subscription order."""

    def __init__(self):
        self._handlers = defaultdict(list)

    def subscribe(self, topic, handler):
        self._handlers[topic].append(handler)
        return handler

    def publish(self, topic, payload):
        results = []
        for handler in list(self._handlers[topic]):
            results.append(handler(payload))
        return results


def build_pipeline(ledger, sink, threshold, review_log):
    """Create a bus with the worker and the monitor handlers registered."""
    bus = EventBus()
    register_upstream_worker(bus, ledger)
    register_control_monitor(bus, sink, threshold, review_log)
    return bus


def run_queue(bus, requests):
    """Publish queued requests in order; return how many were processed."""
    processed = 0
    for request in requests:
        bus.publish(REQUESTED, request)
        processed += 1
    return processed
