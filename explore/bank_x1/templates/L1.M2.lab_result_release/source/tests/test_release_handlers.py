from collections import deque

from labportal.events import RELEASE_COMPLETED, RELEASE_HELD, EventBus
from labportal.pipeline import build_pipeline
from labportal.portal_client import PortalClient
from labportal.release_handlers import ReleaseHoldPolicy


class FakeTransport:
    def __init__(self):
        self.sent = []

    def send(self, method, path, body):
        self.sent.append((method, path, body))
        return {"release_id": f"REL-{len(self.sent):04d}", "status": "published"}


def make_pipeline(held=()):
    bus = EventBus()
    transport = FakeTransport()
    completed, held_events = [], []
    bus.subscribe(RELEASE_COMPLETED, completed.append)
    bus.subscribe(RELEASE_HELD, held_events.append)
    client = build_pipeline(PortalClient(transport), audit_hook=lambda event: None,
                            hold_policy=ReleaseHoldPolicy(held), bus=bus)
    return client, transport, completed, held_events


def request(accession, kind="final", test_code="GLU"):
    return {"patient_id": "P-77", "accession": accession, "test_code": test_code,
            "value": 5.4, "unit": "mmol/L", "ref_low": 3.9, "ref_high": 5.6, "kind": kind}


def test_final_result_released_through_v2_endpoint():
    client, transport, completed, _ = make_pipeline()
    client.submit(request("ACC-1"))
    method, path, body = transport.sent[0]
    assert (method, path) == ("POST", "/v2/releases")
    assert body["accession"] == "ACC-1" and body["kind"] == "final"
    assert completed[0]["accession"] == "ACC-1"
    assert completed[0]["release_id"] == "REL-0001"


def test_amended_result_uses_same_endpoint():
    client, transport, completed, _ = make_pipeline()
    client.submit(request("ACC-2", kind="amended"))
    assert [b["kind"] for _, _, b in transport.sent] == ["amended"]
    assert completed[0]["release_id"] == "REL-0001"


def test_held_result_not_sent_to_portal():
    client, transport, completed, held_events = make_pipeline(held={"HIV1"})
    client.submit(request("ACC-3", test_code="HIV1"))
    assert transport.sent == []
    assert completed == []
    assert held_events[0]["accession"] == "ACC-3"


def test_drain_releases_queue_in_order():
    client, transport, completed, _ = make_pipeline()
    queue = deque([request("ACC-4"), request("ACC-5", kind="amended")])
    assert client.drain(queue) == 2
    assert [c["accession"] for c in completed] == ["ACC-4", "ACC-5"]
    assert [b["payload"]["lines"][0] for _, _, b in transport.sent] == ["GLU: 5.4 mmol/L"] * 2
