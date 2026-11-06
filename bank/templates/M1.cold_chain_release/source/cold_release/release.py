"""Physical release of a pallet to an outbound dock."""
from .models import ReleaseRequest


def release_pallet(dock_controller, request: ReleaseRequest) -> bool:
    """Open the dock bay for the pallet. Only called after the gate said RELEASE."""
    dock_controller.open_bay(request.dock, request.pallet_id)
    return True
