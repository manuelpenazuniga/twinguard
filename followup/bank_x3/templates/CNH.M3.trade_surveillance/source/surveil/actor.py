"""Order placement loop: works order requests from a queue through compliance review."""
from collections import deque
from dataclasses import dataclass

from .models import Order, Side


@dataclass
class Outcome:
    order_id: str
    status: str


class MonitoredActor:
    """Places the orders it receives, each one gated by a compliance review."""

    def __init__(self, compliance, executor, book):
        self.compliance = compliance
        self.executor = executor
        self.book = book

    @staticmethod
    def parse_request(request):
        return Order(order_id=str(request["order_id"]), account=str(request["account"]),
                     symbol=str(request["symbol"]).upper(), side=Side(request["side"]),
                     quantity=int(request["quantity"]))

    def place_order(self, order):
        report = self.compliance.review(order)
        if report.blocked:
            return Outcome(order.order_id, "blocked")
        self.executor.submit(order)
        self.book.apply(order)
        return Outcome(order.order_id, "placed")

    def run(self, requests):
        queue = deque(requests)
        outcomes = []
        while queue:
            outcomes.append(self.place_order(self.parse_request(queue.popleft())))
        return outcomes
