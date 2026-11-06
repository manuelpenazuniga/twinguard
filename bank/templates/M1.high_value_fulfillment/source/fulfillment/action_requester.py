"""Release request intake.

Turns raw entries from the release queue into ``ReleaseRequest`` records and
skips entries that are not waiting for release (already shipped, cancelled or
below the high-value floor, which the standard flow handles).
"""
from dataclasses import dataclass

HIGH_VALUE_FLOOR_CENTS = 100_000
REQUIRED_FIELDS = ("order_id", "customer_id", "amount_cents", "currency", "ship_to_country")


@dataclass(frozen=True)
class ReleaseRequest:
    order_id: str
    customer_id: str
    amount_cents: int
    currency: str
    ship_to_country: str
    address_changed: bool = False


def parse_request(entry):
    """Build a ``ReleaseRequest`` from one queue entry (a dict)."""
    missing = [name for name in REQUIRED_FIELDS if entry.get(name) in (None, "")]
    if missing:
        raise ValueError(f"queue entry missing fields: {', '.join(missing)}")
    amount = int(entry["amount_cents"])
    if amount <= 0:
        raise ValueError(f"order {entry['order_id']}: amount must be positive")
    return ReleaseRequest(
        order_id=str(entry["order_id"]),
        customer_id=str(entry["customer_id"]),
        amount_cents=amount,
        currency=str(entry["currency"]).upper(),
        ship_to_country=str(entry["ship_to_country"]).upper(),
        address_changed=bool(entry.get("address_changed", False)),
    )


def pending_requests(entries):
    """Return the requests from ``entries`` that are queued for release."""
    requests = []
    for entry in entries:
        if entry.get("status", "queued") != "queued":
            continue
        request = parse_request(entry)
        if request.amount_cents < HIGH_VALUE_FLOOR_CENTS:
            continue
        requests.append(request)
    return requests
