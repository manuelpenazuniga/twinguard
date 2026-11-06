"""Drains the setpoint request queue and applies authorized changes."""
from .models import Decision, RunReport
from .units import describe_change


class ActionRequester:
    def __init__(self, auditor, gateway, log=None):
        self._auditor = auditor
        self._gateway = gateway
        self._log = log if log is not None else []

    @property
    def log(self) -> list:
        return self._log

    def run(self, queue) -> RunReport:
        report = RunReport()
        for change in queue:
            self._process(change, report)
        return report

    def _process(self, change, report: RunReport) -> None:
        decision = self._auditor.authorize(change)
        if decision is Decision.ALLOW:
            self._gateway.apply_setpoint(change)
            report.applied.append(change.change_id)
        elif decision is Decision.HOLD:
            report.held.append(change.change_id)
        else:
            report.denied.append(change.change_id)
        self._log.append(f"{decision.value:<5} {describe_change(change)}")
