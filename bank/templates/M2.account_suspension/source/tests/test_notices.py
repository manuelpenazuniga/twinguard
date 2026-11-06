from suspensions.models import Action, OutcomeStatus, SuspensionRequest
from suspensions.notices import render_notice


def test_long_reason_is_truncated():
    request = SuspensionRequest("r-1", "acct-1", Action.SUSPEND, "spam " * 40)
    notice = render_notice(request, OutcomeStatus.APPLIED)
    assert "..." in notice
    assert notice.endswith("Reference: r-1.")


def test_rejected_has_no_notice():
    request = SuspensionRequest("r-2", "acct-2", Action.SUSPEND, "harassment reports")
    assert render_notice(request, OutcomeStatus.REJECTED) == ""
