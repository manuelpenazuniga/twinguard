"""Shared decision values for the high-value release flow."""
from enum import Enum


class Decision(Enum):
    """Outcome of the release gate for one queued order.

    RELEASE: the order may be handed to the carrier now.
    HOLD:    the order stays in the release queue and is picked up again by a
             later run or by the fulfillment review desk.
    DENY:    the order is blocked and routed to the fraud team.
    """

    RELEASE = "release"
    HOLD = "hold"
    DENY = "deny"


class PolicyTimeout(Exception):
    """The fraud policy service did not answer within the configured timeout."""

    def __init__(self, order_id, timeout_s=None):
        self.order_id = order_id
        self.timeout_s = timeout_s
        super().__init__(f"fraud policy service timed out for order {order_id}")
