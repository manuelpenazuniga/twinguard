"""Upstream relay worker: takes relay requests off the queue and hands them to the MTA."""
from relay.formatting import render_message
from relay.models import BatchOutcome, RelayRefused, RelayReport

MAX_BATCH = 50


class UpstreamWorker:
    """Splits each relay request into recipient batches and submits them."""

    def __init__(self, transport, guard, policy, batch_size=MAX_BATCH):
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        self._transport = transport
        self._guard = guard
        self._policy = policy
        self._batch_size = batch_size

    def drain(self, queue):
        """Process every request in queue order and return the reports."""
        reports = []
        while queue:
            reports.append(self.process(queue.popleft()))
        return reports

    def process(self, request):
        if not self._policy.allows(request.sender):
            raise RelayRefused(f"sender {request.sender} is blocked")
        recipients = self._policy.deliverable(request.recipients)
        report = RelayReport(request.request_id)
        for index, chunk in enumerate(self._chunks(recipients), start=1):
            ref = f"{request.request_id}-{index:03d}"
            report.batches.append(self._relay_batch(request, ref, chunk))
        return report

    def _chunks(self, recipients):
        for start in range(0, len(recipients), self._batch_size):
            yield tuple(recipients[start:start + self._batch_size])

    def _relay_batch(self, request, ref, recipients):
        message = render_message(request, ref)
        queue_id = self._transport.send(request.sender, recipients, message, ref)
        self._guard.record_batch(ref, request.sender, recipients, "queued")
        return BatchOutcome(ref, queue_id, "queued", recipients)
