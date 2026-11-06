"""Example adapter for the WES release gateway v2, maintained by the WES team.

Shows how a client builds a ``ReleaseOrder``, calls ``gateway.submit`` and maps the
``ReleaseReceipt`` (including idempotent duplicates) and ``ReleaseRejected``.
"""
from picking.models import ReleaseOrder, ReleaseRejected, WaveResult
from picking.routing import SerpentineRouter


class WaveReleaseAdapter:
    def __init__(self, gateway, router=None):
        self._gateway = gateway
        self._router = router or SerpentineRouter()

    def release_wave(self, request):
        order = ReleaseOrder(
            wave_id=request.wave_id,
            zone=request.zone,
            pick_sequence=self._router.sequence(request.lines),
            priority=request.kind,
        )
        try:
            receipt = self._gateway.submit(order)
        except ReleaseRejected as exc:
            return WaveResult(request.wave_id, "rejected", detail=exc.reason)
        detail = "duplicate" if receipt.duplicate else ""
        return WaveResult(request.wave_id, "released", release_id=receipt.release_id, detail=detail)
