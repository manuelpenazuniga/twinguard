"""Core data types shared by the dispatch worker."""
from dataclasses import dataclass, field
from enum import Enum

ROUTE_CLASSES = ("urban", "regional", "hazmat")


class Decision(Enum):
    """Outcome of the route-permit gate for a single request."""

    ALLOW = "allow"
    DENY = "deny"
    HOLD = "hold"  # not decided yet; re-evaluated on the next queue pass


class PermitServiceTimeout(Exception):
    """The permit policy service did not answer within the configured budget."""

    def __init__(self, request_id, timeout_s):
        super().__init__(f"permit lookup for {request_id} timed out after {timeout_s}s")
        self.request_id = request_id
        self.timeout_s = timeout_s


class InvalidRequest(ValueError):
    """A queue message could not be turned into a dispatch request."""


@dataclass(frozen=True)
class DispatchRequest:
    request_id: str
    vehicle_id: str
    route_id: str
    route_class: str
    depot: str
    pickup_window: str
    tags: tuple = field(default_factory=tuple)
