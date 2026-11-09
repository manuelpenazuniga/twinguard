"""Daily digest sender, already migrated to the ``MtaClient`` submission API.

Use this module as the reference when moving other senders off ``SmtpPool``:
build an ``Envelope`` per batch, call ``submit`` and keep the receipt status.
"""
from relay.formatting import render_message
from relay.models import BatchOutcome
from relay.mta import Envelope


class DigestSender:
    def __init__(self, transport, batch_size=50):
        self._transport = transport
        self._batch_size = batch_size

    def send_digest(self, digest):
        outcomes = []
        recipients = list(digest.recipients)
        for index, start in enumerate(range(0, len(recipients), self._batch_size), start=1):
            chunk = tuple(recipients[start:start + self._batch_size])
            ref = f"{digest.request_id}-{index:03d}"
            envelope = Envelope(ref, digest.sender, chunk, render_message(digest, ref))
            receipt = self._transport.submit(envelope)
            outcomes.append(BatchOutcome(ref, receipt.queue_id, receipt.status, chunk))
        return outcomes
