from renewals.monitored_actor import RenewalRequest
from renewals.registry import PrescriberRegistry
from renewals.wiring import build_pipeline

DR_LEE = "1093817465"
DR_OKAFOR = "1548203967"


class RecordingGateway:
    def __init__(self):
        self.sent = []

    def transmit(self, payload):
        self.sent.append(payload)


class DiscardingSink:
    def publish(self, channel, message):
        pass


def make_pipeline():
    registry = PrescriberRegistry({"RX-1001": DR_LEE, "RX-1002": DR_OKAFOR})
    gateway = RecordingGateway()
    return build_pipeline(registry, gateway, DiscardingSink()), gateway


def request(request_id, rx="RX-1001", npi=DR_LEE, days=30):
    return RenewalRequest(request_id, "PT-55810234", rx, npi, "lisinopril 10mg", days)


def test_consistent_renewal_is_dispatched():
    pipeline, gateway = make_pipeline()
    pipeline.actor.submit_renewal(request("RN-1"))
    assert [p["request_id"] for p in gateway.sent] == ["RN-1"]
    assert gateway.sent[0]["patient"] == "*******0234"


def test_mismatched_prescriber_is_not_dispatched():
    pipeline, gateway = make_pipeline()
    pipeline.actor.submit_renewal(request("RN-2", npi=DR_OKAFOR))
    assert gateway.sent == []
    assert pipeline.dispatcher.review_queue[0]["reason"] == "prescriber_mismatch"


def test_unknown_prescription_is_held():
    pipeline, gateway = make_pipeline()
    pipeline.actor.submit_renewal(request("RN-3", rx="RX-9999"))
    assert gateway.sent == []
    assert pipeline.dispatcher.review_queue[0]["reason"] == "prescriber_unknown"


def test_stale_renewal_is_held_for_review():
    pipeline, gateway = make_pipeline()
    pipeline.actor.submit_renewal(request("RN-4", days=400))
    assert gateway.sent == []
    assert pipeline.dispatcher.review_queue == [{
        "request_id": "RN-4",
        "reason": "stale_prescription",
        "summary": "RN-4: Stale prescription (lisinopril 10mg)",
    }]


def test_drain_continues_after_stale_renewal():
    pipeline, gateway = make_pipeline()
    for r in (request("RN-5", days=365), request("RN-6", rx="RX-1002", npi=DR_OKAFOR)):
        pipeline.actor.enqueue(r)
    assert pipeline.actor.drain() == 2
    assert pipeline.actor.pending() == 0
    assert [p["request_id"] for p in gateway.sent] == ["RN-6"]
