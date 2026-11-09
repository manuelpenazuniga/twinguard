import pytest

from wardplan.census import load_census
from wardplan.monitored_actor import process_queue, shift_summary


def census(cleaning=False):
    return load_census([
        {"ward_id": "5E", "unit_type": "surgical", "beds": 20, "nurses_on_shift": 4,
         "patients": ["a", "b"], "cleaning": cleaning},
        {"ward_id": "ICU1", "unit_type": "icu", "beds": 8, "nurses_on_shift": 2,
         "patients": ["c", "d", "e", "f"]},
    ])


def req(rid, ward, patient):
    return {"request_id": rid, "ward_id": ward, "patient_id": patient}


def run(requests, wards):
    applied = []
    outcome = process_queue(requests, wards, applied.append, lambda alert: None)
    return outcome, applied


def test_assignment_within_capacity_is_applied():
    wards = census()
    outcome, applied = run([req("R1", "5E", "p1")], wards)
    assert outcome["applied"] == ["R1"]
    assert [r["request_id"] for r in applied] == ["R1"]
    assert "p1" in wards["5E"]["patients"]


def test_assignment_over_staffed_capacity_is_held():
    wards = census()
    outcome, applied = run([req("R2", "ICU1", "p2")], wards)
    assert outcome["held"] == ["R2"]
    assert applied == []
    assert [r["severity"] for r in outcome["reports"]] == ["critical"]


def test_cleaning_ward_assignment_is_applied():
    wards = census(cleaning=True)
    outcome, applied = run([req("R3", "5E", "p3"), req("R4", "5E", "p4")], wards)
    assert outcome["applied"] == ["R3", "R4"]
    assert len(applied) == 2
    assert [r["severity"] for r in outcome["reports"]] == ["info", "info"]


def test_batch_continues_after_cleaning_report():
    wards = census(cleaning=True)
    outcome, _ = run([req("R5", "5E", "p5"), req("R6", "ICU1", "p6")], wards)
    assert outcome["applied"] == ["R5"]
    assert outcome["held"] == ["R6"]


def test_missing_fields_rejected():
    with pytest.raises(ValueError):
        run([{"request_id": "R7", "ward_id": "5E"}], census())


def test_shift_summary():
    wards = census()
    outcome, _ = run([req("R8", "5E", "p8")], wards)
    text = shift_summary(outcome, wards)
    assert text.splitlines()[0] == "1 assignment applied, 0 held"
    assert "5E (surgical): 3/20 staffed beds, 15%" in text
