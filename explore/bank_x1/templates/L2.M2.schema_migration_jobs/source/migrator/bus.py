"""In-process event bus used to wire migration job handlers together."""
from collections import defaultdict

DDL_PREFIX = "ddl."
DROP_COLUMN = DDL_PREFIX + "drop_column"
DROP_TABLE = DDL_PREFIX + "drop_table"
ADD_COLUMN = DDL_PREFIX + "add_column"
CHANGE_APPLIED = "change_control.destructive_applied"


def topic_for(kind):
    """Topic on which requests of the given kind are published."""
    return DDL_PREFIX + kind


class EventBus:
    """Synchronous publish/subscribe; handler exceptions propagate to the publisher."""

    def __init__(self):
        self._handlers = defaultdict(list)

    def subscribe(self, topic, handler):
        self._handlers[topic].append(handler)

    def publish(self, topic, payload):
        """Call every handler for ``topic`` in order and return their replies."""
        return [handler(payload) for handler in list(self._handlers[topic])]

    def topics(self):
        return sorted(t for t, hs in self._handlers.items() if hs)
