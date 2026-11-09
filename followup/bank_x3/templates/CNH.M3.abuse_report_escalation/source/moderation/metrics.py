"""Throughput counters for the moderation queue.

{{UNRELATED_NOTE}}
"""
from collections import Counter


class QueueMetrics:
    def __init__(self):
        self._events = Counter()
        self._categories = Counter()

    def record(self, event):
        self._events[event.name] += 1
        category = event.payload.get("category")
        if category:
            self._categories[(event.name, category)] += 1

    def count(self, name):
        return self._events[name]

    def by_category(self, name):
        return {cat: n for (ev, cat), n in sorted(self._categories.items()) if ev == name}

    def snapshot(self):
        return dict(sorted(self._events.items()))
