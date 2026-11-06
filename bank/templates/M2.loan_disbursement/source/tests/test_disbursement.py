from collections import deque

from tranche_desk.bus import TRANCHE_DISBURSED, TRANCHE_REJECTED, EventBus
from tranche_desk.disbursement import Facility, register
from tranche_desk.payments import TransferReceipt
from tranche_desk.upstream_worker import UpstreamWorker
from tranche_desk.watch_guard import WatchGuard


class FakePaymentsClient:
    def __init__(self):
        self.instructions = []

    def submit(self, instruction):
        self.instructions.append(instruction)
        return TransferReceipt(instruction.reference,
                               f"TX-{len(self.instructions):04d}", "accepted")


def make_desk(requests):
    bus = EventBus()
    client = FakePaymentsClient()
    facilities = {"L-100": Facility("L-100", 500_000, "FUND-01")}
    register(bus, client, WatchGuard([]), facilities)
    worker = UpstreamWorker(bus, deque(requests))
    return bus, client, facilities, worker


def req(tranche_id, amount, loan="L-100"):
    return {"tranche_id": tranche_id, "loan_id": loan, "amount_cents": amount,
            "borrower_account": "BRW-77"}


def test_approved_tranche_is_transferred():
    bus, client, facilities, worker = make_desk([req("1", 200_000)])
    assert worker.run_once() == 1
    assert len(client.instructions) == 1
    instruction = client.instructions[0]
    assert instruction.debit_account == "FUND-01"
    assert instruction.credit_account == "BRW-77"
    assert instruction.amount_cents == 200_000
    assert facilities["L-100"].disbursed_cents == 200_000
    assert bus.events(TRANCHE_DISBURSED) == [
        {"tranche_id": "1", "transfer_id": "TX-0001", "status": "accepted"}]


def test_tranche_over_remaining_facility_is_rejected():
    bus, client, facilities, worker = make_desk([req("2", 600_000)])
    worker.run_once()
    assert client.instructions == []
    [event] = bus.events(TRANCHE_REJECTED)
    assert event["tranche_id"] == "2"
    assert "exceeds remaining facility" in event["reason"]


def test_unknown_facility_is_rejected():
    bus, client, _, worker = make_desk([req("3", 1_000, loan="L-404")])
    worker.run_once()
    assert client.instructions == []
    assert bus.events(TRANCHE_REJECTED)[0]["reason"] == "unknown facility"
