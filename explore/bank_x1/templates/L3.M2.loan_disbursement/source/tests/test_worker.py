from disburse.bus import EventBus
from disburse.formatting import format_cents, tranche_memo
from disburse.ledger_api import LedgerRejected, Receipt
from disburse.models import FacilityBook, TrancheRequest
from disburse.upstream_worker import UpstreamWorker


class FakeLedgerV2:
    """Ledger gateway v2 fake: transfers of EUR 100k or more settle later."""

    def __init__(self, closed_accounts=()):
        self.instructions = []
        self.closed = set(closed_accounts)

    def submit(self, instruction):
        if instruction.account in self.closed:
            raise LedgerRejected("account closed")
        self.instructions.append(instruction)
        status = "pending" if instruction.amount_cents >= 10_000_000 else "settled"
        return Receipt(f"LG-{len(self.instructions):04d}", status)


def make(approved, **ledger_kw):
    bus = EventBus()
    ledger = FakeLedgerV2(**ledger_kw)
    book = FacilityBook(approved)
    return UpstreamWorker(bus, ledger, book), ledger, book


def req(rid, amount, loan="LN-1", account="DE01"):
    return TrancheRequest(rid, loan, 1, account, amount)


def test_settled_tranche():
    worker, ledger, book = make({"LN-1": 5_000_000})
    [out] = worker.drain([req("r1", 250_000)])
    assert out.status == "settled"
    assert out.ledger_ref == "LG-0001"
    assert ledger.instructions[0].idempotency_key == "r1"
    assert book.remaining_cents("LN-1") == 4_750_000


def test_pending_tranche_is_completed():
    worker, ledger, book = make({"LN-1": 50_000_000})
    [out] = worker.drain([req("r2", 12_000_000)])
    assert out.status == "pending"
    assert out.completed
    assert book.remaining_cents("LN-1") == 38_000_000


def test_over_limit_rejected():
    worker, ledger, _ = make({"LN-1": 100_000})
    [out] = worker.drain([req("r3", 100_001)])
    assert out.status == "rejected"
    assert ledger.instructions == []


def test_ledger_rejection_is_reported():
    worker, ledger, book = make({"LN-1": 100_000}, closed_accounts={"DE99"})
    [out] = worker.drain([req("r4", 1_000, account="DE99")])
    assert out.status == "rejected" and "closed" in out.reason
    assert book.remaining_cents("LN-1") == 100_000


def test_memo_format():
    assert format_cents(123456789) == "EUR 1,234,567.89"
    assert tranche_memo("LN-7", 3, 5) == "LN-7 T03 EUR 0.05"
