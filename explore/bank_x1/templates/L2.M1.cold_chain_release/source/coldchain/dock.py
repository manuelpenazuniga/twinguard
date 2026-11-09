"""Dock controller wrapper.

The controller is injected as ``release(pallet_id, dock_door)``; calling it
moves the pallet out of refrigerated staging to the given dock door.
"""
import logging

log = logging.getLogger(__name__)


def release_pallet(request, release):
    """Send one pallet from refrigerated staging to its dock door."""
    log.info("releasing pallet %s to door %s", request.pallet_id, request.dock_door)
    release(request.pallet_id, request.dock_door)
    return request.pallet_id
