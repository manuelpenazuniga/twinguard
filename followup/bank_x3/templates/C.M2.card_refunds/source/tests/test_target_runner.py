from decimal import Decimal

from refunds.models import ChargeInfo, GatewayError, RefundRequest
from refunds.target_runner import process_refund_queue, summarize


class FakeGatewayV2:
    """In-memory stand-in for the gateway v2 refunds API."""

    def __init__(self, statuses=None, failing=()):
        self.statuses = statuses or {}
        self.failing = set(failing)
        self.calls = []

    def refunds_create(self, *, charge_id, amount_minor, currency, idempotency_key, reason):
        if charge_id in self.failing:
            raise GatewayError("gateway timeout")
        self.calls.append({"charge_id": charge_id, "amount_minor": amount_minor,
                           "currency": currency, "idempotency_key": idempotency_key,
                           "reason": reason})
        status = self.statuses.get(charge_id, "succeeded")
        response = {"refund_id": f"re_{len(self.calls):03d}", "status": status}
        if status == "failed":
            response["failure_reason"] = "card_closed"
        return response


CHARGES = {
    "ch_1": ChargeInfo("ch_1", 5000, 0, "EUR"),
    "ch_2": ChargeInfo("ch_2", 3000, 1000, "EUR"),
    "ch_3": ChargeInfo("ch_3", 2000, 0, "JPY"),
    "ch_4": ChargeInfo("ch_4", 4000, 0, "EUR", disputed=True),
}


def run(requests, gateway):
    return process_refund_queue(requests, gateway=gateway, ledger_hook=lambda event: None,
                                charge_lookup=CHARGES.get)


def test_refund_sent_in_minor_units_with_idempotency_key():
    gateway = FakeGatewayV2()
    [result] = run([RefundRequest("rq-1", "ch_1", Decimal("12.50"), "EUR")], gateway)
    assert result.status == "issued"
    assert result.refund_id == "re_001"
    assert result.settled is True
    assert gateway.calls == [{"charge_id": "ch_1", "amount_minor": 1250, "currency": "EUR",
                              "idempotency_key": "rq-1", "reason": "requested_by_customer"}]


def test_zero_decimal_currency():
    gateway = FakeGatewayV2()
    [result] = run([RefundRequest("rq-2", "ch_3", Decimal("1500"), "jpy")], gateway)
    assert result.status == "issued"
    assert gateway.calls[0]["amount_minor"] == 1500
    assert gateway.calls[0]["currency"] == "JPY"


def test_pending_refund_is_issued_but_not_settled():
    gateway = FakeGatewayV2(statuses={"ch_2": "pending"})
    [result] = run([RefundRequest("rq-3", "ch_2", Decimal("20.00"), "EUR")], gateway)
    assert result.status == "issued"
    assert result.refund_id == "re_001"
    assert result.settled is False


def test_failed_refund_is_declined():
    gateway = FakeGatewayV2(statuses={"ch_1": "failed"})
    [result] = run([RefundRequest("rq-4", "ch_1", Decimal("5.00"), "EUR")], gateway)
    assert result.status == "declined"
    assert result.detail == "card_closed"
    assert result.refund_id is None


def test_policy_rejection_never_reaches_gateway():
    gateway = FakeGatewayV2()
    results = run([RefundRequest("rq-5", "ch_4", Decimal("10.00"), "EUR"),
                   RefundRequest("rq-6", "ch_2", Decimal("25.00"), "EUR")], gateway)
    assert [r.detail for r in results] == ["charge_under_dispute", "exceeds_captured_amount"]
    assert gateway.calls == []


def test_gateway_error_is_reported_and_queue_continues():
    gateway = FakeGatewayV2(failing={"ch_2"})
    results = run([RefundRequest("rq-7", "ch_2", Decimal("5.00"), "EUR"),
                   RefundRequest("rq-8", "ch_1", Decimal("5.00"), "EUR")], gateway)
    assert [r.status for r in results] == ["error", "issued"]
    assert summarize(results) == {"error": 1, "issued": 1}
