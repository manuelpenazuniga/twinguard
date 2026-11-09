from picking.compliance import ComplianceCheck
from picking.models import (EXPEDITE, PickLine, ReleaseReceipt, ReleaseRejected,
                            WaveRequest)
from picking.runner import TargetRunner


class ListSink:
    def __init__(self):
        self.entries = []

    def write(self, entry):
        self.entries.append(entry)


class Locks:
    def __init__(self, frozen=()):
        self.frozen = set(frozen)

    def is_frozen(self, zone):
        return zone in self.frozen


class GatewayV2:
    """In-memory WES gateway speaking the v2 API only."""

    def __init__(self, known=(), refuse=()):
        self.orders = []
        self.known = set(known)
        self.refuse = set(refuse)

    def submit(self, order):
        if order.wave_id in self.refuse:
            raise ReleaseRejected(order.wave_id, "zone at capacity")
        self.orders.append(order)
        return ReleaseReceipt(f"REL-{order.wave_id}", order.wave_id,
                              duplicate=order.wave_id in self.known)


def lines():
    return (PickLine("SKU-3", "A02-05-1", 1), PickLine("SKU-1", "A01-09-1", 2),
            PickLine("SKU-2", "A01-02-1", 4), PickLine("SKU-4", "A02-11-1", 1))


def make(gateway, frozen=()):
    return TargetRunner(gateway, ComplianceCheck(ListSink(), "DC-7"), Locks(frozen))


def test_release_returns_receipt_id():
    gw = GatewayV2()
    [res] = make(gw).run([WaveRequest("W-1", "A", lines())])
    assert res.status == "released"
    assert res.release_id == "REL-W-1"
    assert [o.wave_id for o in gw.orders] == ["W-1"]


def test_order_carries_serpentine_sequence_and_priority():
    gw = GatewayV2()
    make(gw).run([WaveRequest("W-2", "A", lines(), kind=EXPEDITE)])
    order = gw.orders[0]
    assert [l.location for l in order.pick_sequence] == ["A01-02-1", "A01-09-1",
                                                         "A02-11-1", "A02-05-1"]
    assert order.priority == EXPEDITE


def test_duplicate_receipt_counts_as_released():
    gw = GatewayV2(known={"W-3"})
    [res] = make(gw).run([WaveRequest("W-3", "B", lines())])
    assert (res.status, res.release_id, res.detail) == ("released", "REL-W-3", "duplicate")


def test_rejected_wave_is_reported():
    gw = GatewayV2(refuse={"W-4"})
    results = make(gw).run([WaveRequest("W-4", "B", lines()), WaveRequest("W-5", "B", lines())])
    assert [(r.status, r.detail) for r in results] == [("rejected", "zone at capacity"),
                                                       ("released", "")]


def test_frozen_zone_and_empty_wave_are_held():
    gw = GatewayV2()
    results = make(gw, frozen={"C"}).run([WaveRequest("W-6", "C", lines()),
                                          WaveRequest("W-7", "A", ())])
    assert [r.detail for r in results] == ["zone frozen", "empty wave"]
    assert gw.orders == []
