"""Eligibility rules for erasure requests."""
from dataclasses import dataclass

ERASABLE_TABLES = frozenset({
    "customers",
    "addresses",
    "contact_preferences",
    "support_tickets",
    "web_sessions",
})


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str = ""


def check_eligibility(request, is_on_hold):
    """Decide whether a parsed request may be executed.

    ``is_on_hold`` is a callable taking a customer id and returning True when
    the customer is under a legal hold.
    """
    if not request.identity_verified:
        return Decision(False, "identity not verified")
    if is_on_hold(request.customer_id):
        return Decision(False, "customer under legal hold")
    unknown = sorted(set(request.tables) - ERASABLE_TABLES)
    if unknown:
        return Decision(False, f"tables not erasable: {', '.join(unknown)}")
    return Decision(True)
