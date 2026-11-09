"""Pharmacy hand-off for cleared renewals and the pharmacist review queue."""
from renewals.control_monitor import CLEARED, HELD
from renewals.formatting import mask_identifier, review_summary


class PharmacyDispatcher:
    """Transmits cleared renewals through the injected gateway."""

    def __init__(self, bus, gateway):
        self._gateway = gateway
        self.review_queue = []
        bus.subscribe(CLEARED, self.on_cleared)
        bus.subscribe(HELD, self.on_held)

    def on_cleared(self, event):
        request, _report = event
        self._gateway.transmit({
            "request_id": request.request_id,
            "rx_number": request.rx_number,
            "patient": mask_identifier(request.patient_id),
            "prescriber_npi": request.prescriber_npi,
            "medication": request.medication,
        })

    def on_held(self, event):
        request, report = event
        self.review_queue.append({
            "request_id": request.request_id,
            "reason": report.kind,
            "summary": review_summary(request.request_id, report.kind, request.medication),
        })
