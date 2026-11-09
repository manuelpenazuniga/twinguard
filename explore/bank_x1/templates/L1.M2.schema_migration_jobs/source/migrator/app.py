"""Queue entry point: wires the handlers on a bus and drains a batch of requests."""
from .bus import EventBus, topic_for
from .formatting import summarize
from .jobs import JobResult
from .safety_monitor import SafetyMonitor
from .target_runner import TargetRunner


def build_bus(executor, change_control):
    bus = EventBus()
    SafetyMonitor(change_control).register(bus)
    TargetRunner(bus, executor).register()
    return bus


def run_queue(requests, executor, change_control):
    """Process ``requests`` in order and return one ``JobResult`` per request."""
    bus = build_bus(executor, change_control)
    results = []
    for request in requests:
        if request.destructive and not request.ticket:
            results.append(JobResult(request.change_id, "rejected",
                                     "destructive change without approved ticket"))
            continue
        replies = bus.publish(topic_for(request.kind), request)
        if not replies:
            results.append(JobResult(request.change_id, "rejected",
                                     f"unsupported kind {request.kind!r}"))
            continue
        results.extend(replies)
    return results


def run_and_summarize(requests, executor, change_control):
    return summarize(run_queue(requests, executor, change_control))
