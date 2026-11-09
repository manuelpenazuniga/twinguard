"""Client that applies decisions from the moderation request queue.

Each queue request names a report and an action (``escalate`` or ``close``).
State changes are published on the event bus so other components can react.
"""

REPLY_TEMPLATE = "Thanks for your report {report_id}. Our team has reviewed it: {resolution}."


class UnknownAction(ValueError):
    pass


class ManagedClient:
    def __init__(self, bus, store, messenger, client_id="moderation-worker"):
        self._bus = bus
        self._store = store
        self._messenger = messenger
        self.client_id = client_id

    def handle(self, request):
        report = self._store[request["report_id"]]
        action = request.get("action")
        if action == "escalate":
            return self.escalate_report(report, request)
        if action == "close":
            return self.close_report(report, request)
        raise UnknownAction(action)

    def escalate_report(self, report, request):
        report["escalation_id"] = request["escalation_id"]
        report["status"] = "escalated"
        self._bus.publish("report.escalated", self._payload(report))
        return report["status"]

    def close_report(self, report, request):
        report["status"] = "closed"
        report["resolution"] = request.get("resolution", "no action taken")
        self._bus.publish("report.closed", self._payload(report))
        if report.get("reporter"):
            self._messenger(report["reporter"], REPLY_TEMPLATE.format(
                report_id=report["report_id"], resolution=report["resolution"]))
        return report["status"]

    def drain(self, queue):
        return [self.handle(request) for request in queue]

    def _payload(self, report):
        return {
            "report_id": report["report_id"],
            "category": report["category"],
            "priority": report.get("priority", "normal"),
            "escalation_id": report.get("escalation_id"),
            "status": report["status"],
            "closed_by": self.client_id,
        }
