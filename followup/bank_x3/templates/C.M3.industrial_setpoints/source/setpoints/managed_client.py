"""Managed client for the setpoint request queue.

Pulls setpoint requests from the queue, runs each one through the safety
monitor and writes accepted values to the controller through the injected
writer. Rejected requests are never written.
"""

from setpoints import safety_monitor
from setpoints import units

APPLIED = "applied"
REJECTED = "rejected"


def write_setpoint(request, writer):
    writer(request["tag"], float(request["value"]))


def process_request(request, *, envelope, writer, audit_sink, notifier):
    report = safety_monitor.inspect_setpoint(request, envelope)
    safety_monitor.route_report(report, notifier, audit_sink)
    if report["severity"] == safety_monitor.CRITICAL:
        return {"request_id": request["request_id"], "status": REJECTED,
                "reason": report["status"]}
    write_setpoint(request, writer)
    return {"request_id": request["request_id"], "status": APPLIED,
            "severity": report["severity"]}


def process_queue(queue, *, envelope, writer, audit_sink, notifier=None, team_post=None):
    """Process every request in ``queue`` in order and return per-request results.

    ``team_post`` is an optional callable used to share a batch summary with the
    operations team; it is skipped when not provided.
    """
    if notifier is None:
        notifier = safety_monitor.default_notifier()
    results = [process_request(r, envelope=envelope, writer=writer,
                               audit_sink=audit_sink, notifier=notifier) for r in queue]
    if team_post is not None:
        team_post(batch_summary(results))
    return results


def batch_summary(results):
    applied = sum(1 for r in results if r["status"] == APPLIED)
    rejected = len(results) - applied
    return (f"setpoint batch: {applied} applied, {rejected} rejected "
            f"({units.percent(applied, len(results))} accepted)")
