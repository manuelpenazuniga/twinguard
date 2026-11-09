"""Channel delivery for automatic alerts and team updates.

``transport(channel, text)`` is injected; production wires it to the chat gateway.
"""
from .tariff_format import format_weight

AUDIT_CHANNEL = "#customs-audit"
TEAM_CHANNEL = "#customs-team"


class AlertRejected(ValueError):
    """Raised when something other than a critical finding is sent as an alert."""


def format_alert(alert):
    return (f"[{alert['severity'].upper()}] declaration {alert['declaration_id']}: "
            f"{alert['code']} - {alert['detail']}")


def make_alert_sender(transport):
    """Return ``send_alert(channel, alert)`` delivering critical alerts via ``transport``."""

    def send_alert(channel, alert):
        if alert.get("severity") != "critical":
            raise AlertRejected(f"{channel}: alert sender accepts critical findings only, "
                                f"got {alert.get('severity')!r}")
        transport(channel, format_alert(alert))

    return send_alert


def post_team_update(transport, text):
    """Proactive status message for the brokerage team (digests, progress notes)."""
    transport(TEAM_CHANNEL, text)


def weight_summary(declaration):
    return (f"{declaration['declaration_id']}: gross {format_weight(declaration['gross_weight_kg'])}"
            f" / manifest {format_weight(declaration['manifest_weight_kg'])}")
