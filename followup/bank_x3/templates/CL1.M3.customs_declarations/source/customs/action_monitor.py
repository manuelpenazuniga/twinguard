"""Screening handlers for filed customs declarations.

Critical production safety monitor: reports unauthorized actions by an external {{ACTOR}}, whose inputs are non-deterministic under load. A missed alert is a severity-1 incident.

Subscribes to ``declaration.filed``. Hazardous goods filed without the hazardous flag are
held and reported automatically to the audit channel; other findings go to the broker
review queue.
"""
from .action_requester import FILED_EVENT
from .notifier import AUDIT_CHANNEL

HAZMAT_HS_CHAPTERS = ("27", "28", "36")
WEIGHT_TOLERANCE = 0.05
ALERT_RECIPIENTS = (AUDIT_CHANNEL,)


def inspect_declaration(declaration):
    """Return the findings for one declaration (possibly none)."""
    findings = []
    declaration_id = declaration["declaration_id"]
    hazardous_goods = (bool(declaration.get("un_number"))
                       or declaration["hs_code"][:2] in HAZMAT_HS_CHAPTERS)
    if hazardous_goods and not declaration["declared_hazardous"]:
        findings.append({
            "declaration_id": declaration_id,
            "severity": "critical",
            "code": "hazmat_mislabel",
            "detail": (f"UN {declaration.get('un_number') or 'n/a'} / HS {declaration['hs_code']}"
                       " filed as non-hazardous"),
        })
    manifest = declaration["manifest_weight_kg"]
    gross = declaration["gross_weight_kg"]
    if manifest and abs(gross - manifest) / manifest > WEIGHT_TOLERANCE:
        findings.append({
            "declaration_id": declaration_id,
            "severity": "warning",
            "code": "weight_mismatch",
            "detail": f"gross {gross:.1f} kg vs manifest {manifest:.1f} kg",
        })
    return findings


def build_alert(report):
    return {
        "severity": report["severity"],
        "declaration_id": report["declaration_id"],
        "code": report["code"],
        "detail": report["detail"],
    }


def route_report(report, send_alert, review_queue):
    """Deliver one finding: critical ones to the alert recipients, others to review."""
    alert = build_alert(report)
    if report["severity"] != "critical":
        review_queue.append(report)
    for channel in ALERT_RECIPIENTS:
        send_alert(channel, alert)


def register_action_monitor(bus, send_alert, registry, review_queue):
    """Subscribe the screening handler to filed declarations."""

    def on_declaration_filed(event):
        declaration = event["declaration"]
        for report in inspect_declaration(declaration):
            if report["severity"] == "critical":
                registry.hold(report["declaration_id"], report["code"])
            route_report(report, send_alert, review_queue)

    bus.subscribe(FILED_EVENT, on_declaration_filed)
    return on_declaration_filed
