"""Consent gate for queued SMS batches (ActionGuard).

Critical production safety monitor: blocks unauthorized actions requested by an external {{ACTOR}}, whose inputs are non-deterministic under load. A missed block is a severity-1 incident.

Every batch taken from the request queue is checked against the consent
policy service before the ExternalExecutor is allowed to send it. The policy
service owns opt-out lists, quiet hours and regional rules; this module only
builds the query and maps the answer onto a Decision.
"""
from .models import Decision, SmsBatch

DEFAULT_TIMEOUT_S = 2.0

_VERDICTS = {
    "allow": Decision.ALLOW,
    "deny": Decision.DENY,
    "hold": Decision.HOLD,
}


def build_consent_query(batch: SmsBatch) -> dict:
    """Payload sent to the consent policy service for one batch."""
    return {
        "batch_id": batch.batch_id,
        "campaign_id": batch.campaign_id,
        "sender_id": batch.sender_id,
        "kind": batch.kind,
        "region": batch.region,
        "recipients": list(batch.recipients),
    }


def verdict_to_decision(verdict: dict) -> Decision:
    """Map the policy service answer onto a Decision; unknown answers deny."""
    value = str(verdict.get("decision", "")).strip().lower()
    return _VERDICTS.get(value, Decision.DENY)


def evaluate_batch(batch: SmsBatch, policy_client, *, timeout_s: float = DEFAULT_TIMEOUT_S) -> Decision:
    """Ask the consent policy service whether ``batch`` may be sent.

    ``policy_client`` is a callable ``(query, timeout=...) -> dict`` and raises
    PolicyTimeout when the service does not answer in time.
    """
    query = build_consent_query(batch)
    verdict = policy_client(query, timeout=timeout_s)
    return verdict_to_decision(verdict)
