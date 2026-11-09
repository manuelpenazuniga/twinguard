"""Value objects shared by the pick-wave release path.

The first group describes what arrives on the release queue and what the runner
reports back. The second group mirrors the WES release gateway v2 API.
"""
from dataclasses import dataclass

STANDARD = "standard"
EXPEDITE = "expedite"


@dataclass(frozen=True)
class PickLine:
    """One line of a pick wave; location is ``<aisle>-<bay>-<level>``, e.g. ``A03-12-2``."""

    sku: str
    location: str
    qty: int


@dataclass(frozen=True)
class WaveRequest:
    """A request to release a pick wave to the floor."""

    wave_id: str
    zone: str
    lines: tuple
    kind: str = STANDARD


@dataclass(frozen=True)
class WaveResult:
    """Outcome of one queued request: ``released``, ``rejected`` or ``held``."""

    wave_id: str
    status: str
    release_id: str | None = None
    detail: str = ""


# --- WES release gateway, API v2 -------------------------------------------


class ReleaseRejected(Exception):
    """Raised by the gateway when it refuses a wave (capacity, unknown zone...)."""

    def __init__(self, wave_id, reason):
        super().__init__(f"{wave_id}: {reason}")
        self.wave_id = wave_id
        self.reason = reason


@dataclass(frozen=True)
class ReleaseOrder:
    """Payload of ``gateway.submit``; ``pick_sequence`` is the routed tuple of PickLine."""

    wave_id: str
    zone: str
    pick_sequence: tuple
    priority: str = STANDARD


@dataclass(frozen=True)
class ReleaseReceipt:
    """Answer of ``gateway.submit``.

    ``duplicate`` is set when the WES already holds the wave; the release is
    idempotent and the wave is live on the floor either way.
    """

    release_id: str
    wave_id: str
    duplicate: bool = False
