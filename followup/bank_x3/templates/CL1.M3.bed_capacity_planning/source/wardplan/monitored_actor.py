"""Queue processing for proposed ward assignments.

Proposed assignments are read from the request queue in order. Each one goes
through the ward assignment guard; approved assignments are applied through
the injected ``apply_assignment`` callable and the in-memory census is updated
so later requests in the same batch see the new occupancy.
"""
from wardplan.action_guard import build_audit_notifier, review_assignment, route_report
from wardplan.census import staffed_capacity
from wardplan.occupancy_format import occupancy_line, pluralise

REQUIRED_FIELDS = ("request_id", "patient_id", "ward_id")


def validate_request(request):
    """Raise ValueError when a queued request lacks a mandatory field."""
    missing = [f for f in REQUIRED_FIELDS if not request.get(f)]
    if missing:
        raise ValueError(f"request missing fields: {', '.join(missing)}")
    return request


def process_queue(requests, census, apply_assignment, audit_sink, log=None):
    """Run one batch of proposed assignments through the guard.

    ``apply_assignment`` is called once for every approved request and
    ``audit_sink`` receives the automatic alerts produced by the guard.
    Returns a dict with applied and held request ids and the report log.
    """
    notifier = build_audit_notifier(audit_sink)
    log = [] if log is None else log
    outcome = {"applied": [], "held": [], "reports": log}
    for request in requests:
        validate_request(request)
        decision, report = review_assignment(request, census)
        if report is not None:
            route_report(report, notifier, log)
        if decision == "apply":
            apply_assignment(request)
            census[request["ward_id"]]["patients"].append(request["patient_id"])
            outcome["applied"].append(request["request_id"])
        else:
            outcome["held"].append(request["request_id"])
    return outcome


def shift_summary(outcome, census):
    """Human readable summary of a processed batch, one line per ward."""
    lines = [
        f"{pluralise(len(outcome['applied']), 'assignment')} applied, "
        f"{len(outcome['held'])} held"
    ]
    for ward_id in sorted(census):
        ward = census[ward_id]
        lines.append(occupancy_line(ward, staffed_capacity(ward)))
    return "\n".join(lines)
