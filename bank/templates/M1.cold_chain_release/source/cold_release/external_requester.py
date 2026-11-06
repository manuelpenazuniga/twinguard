"""Queue worker for pallet release requests.

Requests are read from the release queue, passed through the release gate and,
when approved, handed to the dock controller. Held requests are reported so
the next cycle picks them up again.
"""
from .models import Decision, Outcome, ReleaseRequest
from .policy_client import DEFAULT_TIMEOUT_S
from .release import release_pallet
from .safety_monitor import check_release

REQUIRED_FIELDS = ("request_id", "pallet_id", "product_class", "dock", "probe_temp_c")


def parse_message(message: dict) -> ReleaseRequest:
    missing = [f for f in REQUIRED_FIELDS if f not in message]
    if missing:
        raise ValueError(f"release message missing fields: {', '.join(missing)}")
    return ReleaseRequest(
        request_id=str(message["request_id"]),
        pallet_id=str(message["pallet_id"]),
        product_class=str(message["product_class"]),
        dock=str(message["dock"]),
        probe_temp_c=float(message["probe_temp_c"]),
    )


def process_request(request, transport, dock_controller, notifier,
                    timeout_s=DEFAULT_TIMEOUT_S) -> Outcome:
    decision, reason = check_release(transport, request, timeout_s)
    released = False
    if decision is Decision.RELEASE:
        released = release_pallet(dock_controller, request)
    elif decision is Decision.HOLD:
        notifier(f"{request.request_id}: pallet {request.pallet_id} held ({reason})")
    else:
        notifier(f"{request.request_id}: pallet {request.pallet_id} denied ({reason})")
    return Outcome(request.request_id, request.pallet_id, decision, released, reason)


def process_queue(messages, transport, dock_controller, notifier,
                  timeout_s=DEFAULT_TIMEOUT_S) -> list:
    """Process every queued message in order and return one Outcome per message."""
    outcomes = []
    for message in messages:
        request = message if isinstance(message, ReleaseRequest) else parse_message(message)
        outcomes.append(process_request(request, transport, dock_controller, notifier, timeout_s))
    return outcomes


def summarize(outcomes) -> dict:
    counts = {d.value: 0 for d in Decision}
    for outcome in outcomes:
        counts[outcome.decision.value] += 1
    counts["total"] = len(outcomes)
    return counts
