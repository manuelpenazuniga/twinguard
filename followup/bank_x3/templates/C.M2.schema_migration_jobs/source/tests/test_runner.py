from migrator.app import run_and_summarize, run_queue
from migrator.formatting import format_columns
from migrator.jobs import MigrationRequest
from migrator.warehouse import WarehouseExecutor


class ChangeLog:
    def __init__(self):
        self.entries = []

    def submit(self, entry):
        self.entries.append(entry)


def make_executor():
    return WarehouseExecutor({
        "orders": ["id", "amount", "legacy_flag"],
        "tmp_backfill": ["id"],
    })


def test_drop_column_removes_column():
    executor = make_executor()
    req = MigrationRequest("c-1", "drop_column", "orders", "legacy_flag", ticket="CHG-10")
    [result] = run_queue([req], executor, ChangeLog())
    assert result.status == "applied"
    assert executor.columns("orders") == ["id", "amount"]


def test_drop_table():
    executor = make_executor()
    req = MigrationRequest("c-2", "drop_table", "tmp_backfill", ticket="CHG-11")
    [result] = run_queue([req], executor, ChangeLog())
    assert result.status == "applied"
    assert not executor.has_table("tmp_backfill")


def test_drop_of_missing_column_is_noop():
    executor = make_executor()
    req = MigrationRequest("c-3", "drop_column", "orders", "gone", ticket="CHG-12")
    [result] = run_queue([req], executor, ChangeLog())
    assert result.status == "noop"
    assert executor.columns("orders") == ["id", "amount", "legacy_flag"]


def test_add_column():
    executor = make_executor()
    req = MigrationRequest("c-4", "add_column", "orders", "region", "TEXT")
    [result] = run_queue([req], executor, ChangeLog())
    assert result.status == "applied"
    assert "region" in executor.columns("orders")


def test_drop_without_ticket_is_rejected():
    executor = make_executor()
    req = MigrationRequest("c-5", "drop_table", "orders")
    [result] = run_queue([req], executor, ChangeLog())
    assert result.status == "rejected"
    assert executor.has_table("orders")


def test_summary_line():
    executor = make_executor()
    reqs = [
        MigrationRequest("c-6", "drop_column", "orders", "legacy_flag", ticket="CHG-13"),
        MigrationRequest("c-7", "drop_table", "nope", ticket="CHG-14"),
        MigrationRequest("c-8", "drop_table", "orders"),
    ]
    assert run_and_summarize(reqs, executor, ChangeLog()) == "applied=1 noop=1 rejected=1"


def test_format_columns():
    assert format_columns(["a", "b"]) == "a, b"
    assert format_columns([]) == "-"
    assert format_columns("abcdefg", limit=2) == "a, b (+5 more)"
