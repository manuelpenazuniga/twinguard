import pytest

from tranche_desk.bus import EventBus
from tranche_desk.formatting import format_cents, tranche_reference
from tranche_desk.payments import PaymentsClient, PaymentsError, TransferInstruction


def test_bus_delivers_in_subscription_order():
    bus, seen = EventBus(), []
    bus.subscribe("t", lambda p: seen.append(("a", p)))
    bus.subscribe("t", lambda p: seen.append(("b", p)))
    bus.publish("t", 1)
    assert seen == [("a", 1), ("b", 1)]
    assert bus.events("t") == [1]


def test_format_cents():
    assert format_cents(123456789) == "1,234,567.89 EUR"
    assert format_cents(-5) == "-0.05 EUR"


def test_tranche_reference():
    assert tranche_reference("L-1", "7") == "L-1/T007"
    assert tranche_reference("L-1", "x") == "L-1/x"


def test_payments_client_v2_submit():
    calls = []

    def transport(path, body):
        calls.append((path, body))
        return {"status": "accepted", "transfer_id": "TX-9"}

    receipt = PaymentsClient(transport).submit(
        TransferInstruction("r1", "FUND-01", "BRW-1", 100))
    assert receipt.transfer_id == "TX-9"
    assert calls[0][0] == "/v2/transfers"


def test_payments_client_refusal():
    client = PaymentsClient(lambda path, body: {"status": "rejected"})
    with pytest.raises(PaymentsError):
        client.submit(TransferInstruction("r2", "FUND-01", "BRW-1", 100))
