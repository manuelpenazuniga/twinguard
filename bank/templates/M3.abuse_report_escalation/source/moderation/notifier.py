"""Delivery of automatic alerts to chat channels.

The transport is injected so the worker can run against the chat gateway in
production and against an in-memory transport in tests.
"""


def render_alert(alert):
    return "[{severity}] report {report_id} ({category}): {reason}".format(
        severity=alert["severity"].upper(),
        report_id=alert["report_id"],
        category=alert.get("category", "unknown"),
        reason=alert.get("reason", ""),
    )


class ChannelNotifier:
    def __init__(self, transport):
        self._transport = transport

    def deliver(self, channel, alert):
        if not channel:
            raise ValueError("alert has no destination channel")
        message = {
            "channel": channel,
            "severity": alert["severity"],
            "report_id": alert["report_id"],
            "text": render_alert(alert),
        }
        self._transport.post(channel, message)
        return message
