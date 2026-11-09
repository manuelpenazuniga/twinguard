"""Drains the queued restock orders for one dispensing cycle."""
from typing import Iterable

from .models import RestockOrder, RunReport


class RestockQueueRunner:
    """Feeds every queued order to the executor and collects a run report.

    Held orders are returned in ``RunReport.held_orders`` so the scheduler can
    put them back on the queue for the next cycle.
    """

    def __init__(self, executor):
        self._executor = executor

    def run(self, orders: Iterable[RestockOrder]) -> RunReport:
        report = RunReport()
        for order in orders:
            result = self._executor.process(order)
            report.record(order, result)
        return report
