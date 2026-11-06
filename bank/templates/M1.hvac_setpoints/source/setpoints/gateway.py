"""Building management system gateway.

Writes setpoints to zone controllers through an injected BACnet-style client.
"""
from .models import SetpointChange
from .units import round_to_controller


class BmsGateway:
    def __init__(self, client):
        self._client = client

    def apply_setpoint(self, change: SetpointChange) -> None:
        point = f"{change.building}/{change.zone}/{change.mode}-setpoint"
        self._client.write_property(point, round_to_controller(change.target_c))
