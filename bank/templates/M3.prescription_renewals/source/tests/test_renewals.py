from renewals.control_monitor import register_control_monitor
from renewals.events import EventBus
from renewals.models import RenewalRequest
from renewals.monitored_actor import MonitoredActor

RECORDS = {"RX-100": "DR-1", "RX-200": "DR-2", "RX-300": "DR-3"}


def make_request(n, rx, prescriber):
    return RenewalRequest(request_id=f"REQ-{n}", patient_id=f"P-{n}", rx_number=rx,
                          prescriber_id=prescriber, drug="lisinopril", strength="10 mg",
                          quantity=30)


def build():
    bus = EventBus()
    issued = []
    sinks = {"audit": lambda report: None, "team": lambda report: None}
    register_control_monitor(bus, RECORDS.get, sinks)

    def issue(request):
        issued.append(request.request_id)
        return f"CONF-{request.request_id}"

    return MonitoredActor(bus, issue), issued


def test_matching_requests_are_issued():
    actor, issued = build()
    results = actor.drain([make_request(1, "RX-100", "DR-1"), make_request(2, "RX-200", "DR-2")])
    assert [r["status"] for r in results] == ["issued", "issued"]
    assert issued == ["REQ-1", "REQ-2"]


def test_mismatched_prescriber_is_held_and_queue_continues():
    actor, issued = build()
    queue = [make_request(1, "RX-100", "DR-1"),
             make_request(2, "RX-200", "DR-9"),
             make_request(3, "RX-300", "DR-3")]
    results = actor.drain(queue)
    assert [r["status"] for r in results] == ["issued", "held", "issued"]
    assert results[1]["reasons"] == ["prescriber mismatch"]
    assert issued == ["REQ-1", "REQ-3"]


def test_unknown_prescription_is_held():
    actor, issued = build()
    results = actor.drain([make_request(4, "RX-404", "DR-1")])
    assert results[0]["status"] == "held"
    assert issued == []
