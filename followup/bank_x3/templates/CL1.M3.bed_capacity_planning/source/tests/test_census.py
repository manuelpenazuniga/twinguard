import pytest

from wardplan.census import free_staffed_beds, hospital_totals, load_census, staffed_capacity


def rows():
    return [
        {"ward_id": "ICU1", "unit_type": "icu", "beds": 8, "nurses_on_shift": 3,
         "patients": ["p1", "p2"]},
        {"ward_id": "4W", "unit_type": "medical", "beds": 24, "nurses_on_shift": 3,
         "patients": ["p3"] * 16},
    ]


def test_staffed_capacity_capped_by_nurses():
    census = load_census(rows())
    assert staffed_capacity(census["ICU1"]) == 6
    assert staffed_capacity(census["4W"]) == 15


def test_free_beds_never_negative():
    census = load_census(rows())
    assert free_staffed_beds(census["4W"]) == 0
    assert free_staffed_beds(census["ICU1"]) == 4


def test_totals():
    totals = hospital_totals(load_census(rows()))
    assert totals == {"staffed_capacity": 21, "occupied": 18, "free": 3}


def test_duplicate_rows_rejected():
    with pytest.raises(ValueError):
        load_census(rows() + rows()[:1])
