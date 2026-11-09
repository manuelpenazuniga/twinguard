from fulfillment.decisions import Decision
from fulfillment.pipeline import run_release_queue


def entry(order_id, amount_cents=250_000, **extra):
    base = {
        "order_id": order_id,
        "customer_id": f"C-{order_id}",
        "amount_cents": amount_cents,
        "currency": "USD",
        "ship_to_country": "US",
        "status": "queued",
    }
    base.update(extra)
    return base


class Carrier:
    def __init__(self):
        self.labels = []

    def __call__(self, label):
        self.labels.append(label)
        return f"TRK-{label['order_id']}"


def policy_from(verdicts, timeouts=()):
    def policy(payload, timeout_s):
        if payload["order_id"] in timeouts:
            raise TimeoutError("read timed out")
        return verdicts.get(payload["order_id"], "approve")
    return policy


def test_approved_orders_are_shipped():
    carrier = Carrier()
    summary = run_release_queue([entry("A"), entry("B", 900_000)],
                                policy=policy_from({}), carrier=carrier)
    assert summary["shipped"] == ["A", "B"]
    assert carrier.labels[1]["signature_required"] is True
    assert carrier.labels[0]["service"] == "express"


def test_review_and_reject_are_not_shipped():
    carrier = Carrier()
    summary = run_release_queue(
        [entry("A"), entry("B"), entry("C")],
        policy=policy_from({"B": "review", "C": "reject"}), carrier=carrier)
    assert summary["held_ids"] == ["B"]
    assert summary["denied_ids"] == ["C"]
    assert [label["order_id"] for label in carrier.labels] == ["A"]


def test_non_queued_and_low_value_entries_are_skipped():
    carrier = Carrier()
    summary = run_release_queue(
        [entry("A", status="shipped"), entry("B", 40_000), entry("C")],
        policy=policy_from({}), carrier=carrier)
    assert summary["processed"] == 1
    assert summary["shipped"] == ["C"]


def test_run_finishes_when_policy_service_times_out():
    carrier = Carrier()
    lines = []
    summary = run_release_queue(
        [entry("A"), entry("B"), entry("C")],
        policy=policy_from({}, timeouts={"B"}), carrier=carrier, log=lines.append)
    assert summary["processed"] == 3
    assert "A" in summary["shipped"] and "C" in summary["shipped"]
    assert lines and lines[0].startswith("release run: 3 processed")


def test_summary_counts():
    summary = run_release_queue(
        [entry("A"), entry("B")],
        policy=policy_from({"A": "review"}), carrier=Carrier())
    assert (summary["released"], summary["held"], summary["denied"]) == (1, 1, 0)
    assert Decision.HOLD.value == "hold"
