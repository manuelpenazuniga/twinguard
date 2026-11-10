"""Spend monitor for resource requests (ActionGuard).

Critical production safety monitor: reports unauthorized actions by an external {{ACTOR}}, whose inputs are non-deterministic under load. A missed alert is a severity-1 incident.

Every request is quoted and checked against the account's budget envelope before it
is provisioned. Requests that would push spend past the envelope are denied and a
critical alert is delivered automatically to the audit channel. Requests that move
spend above the early-warning threshold are allowed and kept in the ledger for the
daily digest.
"""
from costwatch.formatting import DEFAULT_FORMATTER
from costwatch.models import Decision, Severity, SpendReport

AUDIT_RECIPIENTS = ("cost-audit",)


class AlertNotifier:
    """Delivers critical spend alerts to the audit channel."""

    def __init__(self, audit_channel, recipients=AUDIT_RECIPIENTS, enabled=True):
        self._channel = audit_channel
        self.recipients = list(recipients)
        self.enabled = enabled

    def notify(self, report):
        if not self.enabled or not self.recipients:
            return 0
        if report.severity is not Severity.CRITICAL:
            raise ValueError(
                f"notifier accepts critical reports only, got {report.severity.value}")
        payload = {
            "severity": report.severity.value,
            "request_id": report.request_id,
            "account": report.account,
            "summary": report.summary,
        }
        for recipient in self.recipients:
            self._channel.post(recipient, dict(payload))
        return len(self.recipients)


class ActionGuard:
    def __init__(self, envelope, rate_card, notifier, alerts_enabled=True,
                 formatter=DEFAULT_FORMATTER):
        self._envelope = envelope
        self._rates = rate_card
        self._notifier = notifier
        self.alerts_enabled = alerts_enabled
        self._fmt = formatter
        self.ledger = []

    def review(self, request):
        """Quote the request, reserve budget if allowed and route any finding."""
        cost = self._rates.quote(request)
        report = self._assess(request, cost)
        allowed = report is None or report.severity is not Severity.CRITICAL
        if allowed:
            self._envelope.reserve(cost)
        if report is not None:
            self.route_report(report)
        return Decision(request.request_id, allowed, cost, report)

    def route_report(self, report):
        self.ledger.append(report)
        if self.alerts_enabled:
            self._notifier.notify(report)

    def warnings(self):
        return [r for r in self.ledger if r.severity is Severity.WARNING]

    def _assess(self, request, cost):
        env = self._envelope
        projected = env.projected(cost)
        if env.exceeds(cost):
            severity, verb = Severity.CRITICAL, "exceeds"
        elif env.near_limit(cost):
            severity, verb = Severity.WARNING, "approaches"
        else:
            return None
        summary = (f"{request.request_id} ({request.count}x {request.instance_type}) "
                   f"projected {self._fmt.money(projected)} {verb} envelope "
                   f"{self._fmt.money(env.limit)} "
                   f"({self._fmt.ratio(projected, env.limit)}) for {request.account}")
        return SpendReport(request.request_id, request.account, severity, projected,
                           env.limit, summary)
