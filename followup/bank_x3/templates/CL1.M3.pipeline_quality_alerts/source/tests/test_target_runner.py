from loadwatch.formatting import format_count, format_ratio
from loadwatch.target_runner import run_load_job, validate_row


def test_validate_row_reasons():
    ok = {"record_id": "a", "event_time": "t", "amount": 3}
    assert validate_row(ok) is None
    assert validate_row({**ok, "record_id": ""}) == "missing_record_id"
    assert validate_row({**ok, "amount": "3"}) == "bad_amount"
    assert validate_row({**ok, "amount": True}) == "bad_amount"
    assert validate_row(["a"]) == "not_a_record"


def test_run_load_job_counts_and_writes():
    written = []
    rows = [{"record_id": "a", "event_time": "t", "amount": 1},
            {"record_id": "b", "event_time": None, "amount": 2}]
    result = run_load_job({"job_id": "J", "table": "staging.t", "rows": rows},
                          lambda table, accepted: written.append((table, accepted)))
    assert result["loaded_rows"] == 1
    assert result["dropped_rows"] == 1
    assert result["rejections"] == {"missing_event_time": 1}
    assert written == [("staging.t", rows[:1])]


def test_formatting_helpers():
    assert format_count(1234567) == "1,234,567"
    assert format_ratio(1, 3) == "33.3%"
    assert format_ratio(0, 0) == "0.0%"
