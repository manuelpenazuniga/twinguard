"""Queue consumer for pallet release requests.

Requests are read from the release queue in order. Each one is checked by
``safety_monitor.check_release`` and only released pallets reach the dock
controller. Held pallets are returned so the next cycle can re-queue them.
"""
import logging

from coldchain.dock import release_pallet
from coldchain.formatting import format_summary
from coldchain.models import Decision
from coldchain.policy_client import DEFAULT_TIMEOUT_S
from coldchain.safety_monitor import check_release

log = logging.getLogger(__name__)


def new_summary():
    """Empty run summary, keyed by outcome."""
    return {"released": [], "held": [], "denied": []}


def process_request(request, evaluate, release, summary, timeout_s=DEFAULT_TIMEOUT_S):
    """Handle a single queued release request and record its outcome."""
    decision = check_release(request, evaluate, timeout_s)
    if decision is Decision.RELEASE:
        release_pallet(request, release)
        summary["released"].append(request.pallet_id)
    elif decision is Decision.HOLD:
        summary["held"].append(request.pallet_id)
    else:
        summary["denied"].append(request.pallet_id)
    return decision


def process_queue(queue, evaluate, release, timeout_s=DEFAULT_TIMEOUT_S):
    """Drain the release queue and return the run summary."""
    summary = new_summary()
    for request in queue:
        process_request(request, evaluate, release, summary, timeout_s)
    log.info("release run finished: %s", format_summary(summary))
    return summary
