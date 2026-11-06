"""Drains the pick-wave release queue and hands routed waves to the WES gateway."""
from picking.models import EXPEDITE, ReleaseRejected, WaveResult
from picking.routing import SerpentineRouter


class TargetRunner:
    """Processes queued wave requests one by one.

    ``gateway`` talks to the WES, ``compliance`` is the release hook described in
    CONTRIBUTING.md and ``zone_locks`` answers ``is_frozen(zone)`` (cycle counts,
    blocked aisles).
    """

    def __init__(self, gateway, compliance, zone_locks, router=None):
        self._gateway = gateway
        self._compliance = compliance
        self._zone_locks = zone_locks
        self._router = router or SerpentineRouter()

    def run(self, queue):
        """Process every request of ``queue`` in order and return their results."""
        return [self.handle(request) for request in queue]

    def handle(self, request):
        if not request.lines:
            return WaveResult(request.wave_id, "held", detail="empty wave")
        if self._zone_locks.is_frozen(request.zone):
            return WaveResult(request.wave_id, "held", detail="zone frozen")
        return self._release_wave(request)

    def _release_wave(self, request):
        ordered = self._router.sequence(request.lines)
        stops = [(line.location, line.sku, line.qty) for line in ordered]
        try:
            release_id = self._gateway.release(
                request.wave_id, request.zone, stops, rush=request.kind == EXPEDITE
            )
        except ReleaseRejected as exc:
            return WaveResult(request.wave_id, "rejected", detail=exc.reason)
        self._compliance.record_release(request.wave_id, request.zone, request.kind, release_id)
        return WaveResult(request.wave_id, "released", release_id=release_id)
