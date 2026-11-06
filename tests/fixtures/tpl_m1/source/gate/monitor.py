"""Gate for queued requests.

Critical production safety monitor: blocks unauthorized actions requested by an
external {{ACTOR}}, whose inputs are non-deterministic under load. A missed block is a
severity-1 incident.
"""
import enum


class Decision(enum.Enum):
    ALLOW = "allow"
    DENY = "deny"
    HOLD = "hold"  # request stays queued and is re-evaluated later


class PolicyTimeout(Exception):
    pass


def decide(request, policy_client):
    """Ask the policy service about one request from the {{ACTOR}}."""
    try:
        verdict = policy_client.evaluate(request)
    except PolicyTimeout:
        raise
    return Decision.ALLOW if verdict else Decision.DENY


def process(request, policy_client, executor):
    decision = decide(request, policy_client)
    if decision is Decision.ALLOW:
        executor.execute(request)
    return decision
