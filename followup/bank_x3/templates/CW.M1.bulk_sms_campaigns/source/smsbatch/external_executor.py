"""ExternalExecutor: hands approved batches to the SMS gateway.

Each batch is expanded into one message per recipient and submitted through
the injected gateway client, which exposes ``send(message) -> dict``.
"""
from .models import SmsBatch
from .text_utils import normalise_body, segment_count


def build_messages(batch: SmsBatch) -> list[dict]:
    body = normalise_body(batch.body)
    segments = segment_count(body)
    return [
        {
            "batch_id": batch.batch_id,
            "campaign_id": batch.campaign_id,
            "sender_id": batch.sender_id,
            "to": recipient,
            "body": body,
            "segments": segments,
        }
        for recipient in batch.recipients
    ]


def execute_batch(batch: SmsBatch, gateway) -> int:
    """Submit every message of ``batch``; returns how many the gateway accepted."""
    accepted = 0
    for message in build_messages(batch):
        receipt = gateway.send(message) or {}
        if receipt.get("accepted", False):
            accepted += 1
    return accepted
