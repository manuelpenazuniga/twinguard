"""Account-holder notice text for enforcement outcomes.

{{UNRELATED_NOTE}}
"""
from .models import Action, OutcomeStatus

_TEMPLATES = {
    (Action.SUSPEND, OutcomeStatus.APPLIED):
        "Your account has been suspended ({reason}). Reference: {ref}.",
    (Action.SUSPEND, OutcomeStatus.UNCHANGED):
        "Your account remains suspended. Reference: {ref}.",
    (Action.REINSTATE, OutcomeStatus.APPLIED):
        "Your account has been reinstated. Reference: {ref}.",
    (Action.REINSTATE, OutcomeStatus.UNCHANGED):
        "Your account is active. Reference: {ref}.",
}


def render_notice(request, status):
    """Return the notice shown to the account holder, or "" when none applies."""
    template = _TEMPLATES.get((request.action, status))
    if template is None:
        return ""
    reason = " ".join(request.reason.split())
    if len(reason) > 80:
        reason = reason[:77].rstrip() + "..."
    return template.format(reason=reason, ref=request.case_ref or request.request_id)
