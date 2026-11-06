from conftest import message

from erasure.monitored_executor import process_queue
from erasure.report_format import format_summary


def no_holds(customer_id):
    return False


def run(messages, store, is_on_hold=no_holds):
    return process_queue(messages, store=store, audit_hook=lambda event: None,
                         is_on_hold=is_on_hold)


def test_eligible_requests_are_erased(store):
    summary = run([
        message("r-1", "c-100", tables=("customers", "addresses")),
        message("r-2", "c-101"),
    ], store)
    assert summary.failed == []
    assert summary.erased == [("c-100", 4), ("c-101", 2)]
    assert [spec.customer_id for spec in store.specs] == ["c-100", "c-101"]


def test_spec_carries_tables_and_reason(store):
    run([message("r-1", "c-100", tables=("web_sessions", "customers"))], store)
    (spec,) = store.specs
    assert spec.tables == ("customers", "web_sessions")
    assert spec.reason == "gdpr_art17"


def test_legal_hold_blocks_erasure(store):
    summary = run([message("r-1", "c-100"), message("r-2", "c-200")], store,
                  is_on_hold=lambda cid: cid == "c-200")
    assert summary.blocked == [("r-2", "customer under legal hold")]
    assert [spec.customer_id for spec in store.specs] == ["c-100"]


def test_unverified_and_malformed_requests_are_not_erased(store):
    summary = run([
        message("r-1", "c-100", identity_verified=False),
        {"request_id": "r-2", "customer_id": "c-101"},
    ], store)
    assert summary.blocked == [("r-1", "identity not verified")]
    assert summary.rejected[0][0] == "r-2"
    assert store.specs == []


def test_report_lists_totals(store):
    summary = run([message("r-1", "c-100"), message("r-2", "c-101", identity_verified=False)],
                  store)
    report = format_summary(summary)
    assert report.splitlines()[0] == "erased: 1 customer (2 rows)"
    assert "  - r-2: identity not verified" in report
