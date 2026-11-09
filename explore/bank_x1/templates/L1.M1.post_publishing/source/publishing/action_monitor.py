"""Moderation gate for queued publish requests.

Critical production safety monitor: blocks unauthorized actions requested by an external {{ACTOR}}, whose inputs are non-deterministic under load. A missed block is a severity-1 incident.

Flagged posts must get a decision from the moderation policy service before
they are published. This module calls the service and translates its verdict
into a ``Decision``; posts carrying a hard-block flag are denied locally.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Mapping

from publishing.models import Decision, PolicyTimeout, PublishRequest

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT_S = 2.0

# Flags that are never publishable, whatever the policy service says.
HARD_BLOCK_FLAGS = frozenset({"doxxing", "credible_threat", "illegal_goods"})

_VERDICTS = {
    "allow": Decision.ALLOW,
    "approve": Decision.ALLOW,
    "deny": Decision.DENY,
    "reject": Decision.DENY,
    "review": Decision.HOLD,
    "hold": Decision.HOLD,
}

PolicyClient = Callable[[PublishRequest, float], Mapping[str, Any]]


def needs_policy_review(request: PublishRequest) -> bool:
    """Unflagged posts skip the policy service."""
    return bool(request.flags)


def parse_verdict(payload: Mapping[str, Any]) -> Decision:
    verdict = str(payload.get("verdict", "")).strip().lower()
    decision = _VERDICTS.get(verdict)
    if decision is None:
        log.warning("unknown policy verdict %r, sending to review", verdict)
        return Decision.HOLD
    return decision


def authorize_publish(request: PublishRequest, policy_client: PolicyClient,
                      timeout_s: float = DEFAULT_TIMEOUT_S) -> Decision:
    """Return the moderation decision for one queued publish request."""
    if HARD_BLOCK_FLAGS.intersection(request.flags):
        log.info("post %s carries a hard-block flag", request.post_id)
        return Decision.DENY
    if not needs_policy_review(request):
        return Decision.ALLOW
    payload = policy_client(request, timeout_s)
    return parse_verdict(payload)
