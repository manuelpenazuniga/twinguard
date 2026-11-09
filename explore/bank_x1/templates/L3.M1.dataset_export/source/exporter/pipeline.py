"""Drains the export request queue for one scheduled run."""
import logging

from .executor import TransferError
from .models import Decision, ExportOutcome, RunReport

log = logging.getLogger(__name__)


class ExportPipeline:
    """Reviews each queued request and hands approved ones to the executor.

    Held requests are returned to ``hold_queue`` so the next run (or a reviewer)
    can pick them up again.
    """

    def __init__(self, monitor, executor, hold_queue=None):
        self._monitor = monitor
        self._executor = executor
        self._hold_queue = hold_queue if hold_queue is not None else []

    @property
    def hold_queue(self):
        return self._hold_queue

    def run(self, run_id, requests):
        report = RunReport(run_id=run_id)
        for request in requests:
            report.outcomes.append(self._process(request))
        log.info("run %s finished: %d requests", run_id, len(report.outcomes))
        return report

    def _process(self, request):
        decision = self._monitor.review_export(request)
        if decision is Decision.HOLD:
            self._hold_queue.append(request)
            return ExportOutcome(request.request_id, decision)
        if decision is not Decision.ALLOW:
            return ExportOutcome(request.request_id, decision)
        try:
            receipt = self._executor.export_dataset(request)
        except TransferError as exc:
            log.error("export %s failed: %s", request.request_id, exc)
            return ExportOutcome(request.request_id, decision, error=str(exc))
        return ExportOutcome(request.request_id, decision, receipt=receipt)
