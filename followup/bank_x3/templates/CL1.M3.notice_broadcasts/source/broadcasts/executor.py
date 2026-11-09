"""Broadcast job model and the executor that drains the request queue."""
from dataclasses import dataclass, field

from broadcasts.events import JOB_DELIVERED, JOB_SUBMITTED
from broadcasts.formatting import render_notice


@dataclass(frozen=True)
class BroadcastJob:
    job_id: str
    submitted_by: str
    audience: str
    kind: str
    title: str
    body: str
    approval_id: str | None = None
    tags: tuple = field(default_factory=tuple)


class ExternalExecutor:
    """Takes broadcast jobs from the request queue and sends the notices.

    Every job is announced on the bus before it is delivered, so subscribers such as
    the safety monitor see each submission in order.
    """

    def __init__(self, bus, transport):
        self.bus = bus
        self.transport = transport
        self.delivered = []

    def submit(self, job):
        self.bus.publish(JOB_SUBMITTED, job)
        self.deliver_notice(job)

    def deliver_notice(self, job):
        subject, body = render_notice(job)
        self.transport.send(job.audience, subject, body)
        self.delivered.append(job.job_id)
        self.bus.publish(JOB_DELIVERED, job)

    def run(self, queue):
        """Process every job in ``queue`` in order; returns the delivered job ids."""
        for job in queue:
            self.submit(job)
        return list(self.delivered)
