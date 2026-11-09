"""Processes a single restock order against an automated dispensing cabinet."""
from .models import Decision, Outcome, ProcessResult, RestockOrder


class MonitoredExecutor:
    """Runs restock orders, loading a cabinet only after the formulary gate approves.

    ``cabinet`` must provide ``load_restock(cabinet_id, order_id, lines)`` where
    ``lines`` is a list of ``(ndc, quantity)`` pairs.
    """

    def __init__(self, guard, cabinet):
        self._guard = guard
        self._cabinet = cabinet

    def process(self, order: RestockOrder) -> ProcessResult:
        problems = order.validate()
        if problems:
            return ProcessResult(order.order_id, Outcome.REJECTED, "; ".join(problems))

        decision = self._guard.authorize(order)
        if decision is Decision.APPROVE:
            self.execute_restock(order)
            return ProcessResult(order.order_id, Outcome.LOADED)
        if decision is Decision.HOLD:
            return ProcessResult(order.order_id, Outcome.HELD, "awaiting formulary decision")
        return ProcessResult(order.order_id, Outcome.DENIED, "not permitted by formulary")

    def execute_restock(self, order: RestockOrder) -> None:
        lines = [(line.ndc, line.quantity) for line in order.lines]
        self._cabinet.load_restock(order.cabinet_id, order.order_id, lines)
