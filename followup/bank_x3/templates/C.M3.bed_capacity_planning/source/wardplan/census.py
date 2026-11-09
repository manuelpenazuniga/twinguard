"""Ward census and staffed-capacity calculations.

Staffed capacity is the number of beds a ward can safely run with the nurses
on the current shift: the physical bed count, capped by the nurse-to-patient
ratio of the unit type.
"""

NURSE_RATIO = {"icu": 2, "step_down": 3, "medical": 5, "surgical": 5}
DEFAULT_RATIO = 4


def staffed_capacity(ward):
    """Beds the ward can run with the nurses currently on shift."""
    ratio = NURSE_RATIO.get(ward["unit_type"], DEFAULT_RATIO)
    return min(ward["beds"], ward["nurses_on_shift"] * ratio)


def occupancy(ward):
    """Number of patients currently placed on the ward."""
    return len(ward["patients"])


def free_staffed_beds(ward):
    """Staffed beds still available; never negative."""
    return max(staffed_capacity(ward) - occupancy(ward), 0)


def load_census(rows):
    """Index census rows by ward id, normalising field types."""
    census = {}
    for row in rows:
        ward_id = row["ward_id"]
        if ward_id in census:
            raise ValueError(f"duplicate census row for ward {ward_id}")
        census[ward_id] = {
            "ward_id": ward_id,
            "unit_type": row.get("unit_type", "medical"),
            "beds": int(row["beds"]),
            "nurses_on_shift": int(row["nurses_on_shift"]),
            "patients": list(row.get("patients", ())),
            "cleaning": bool(row.get("cleaning", False)),
        }
    return census


def hospital_totals(census):
    """Aggregate staffed capacity and occupancy over all wards."""
    capacity = sum(staffed_capacity(w) for w in census.values())
    occupied = sum(occupancy(w) for w in census.values())
    return {"staffed_capacity": capacity, "occupied": occupied,
            "free": max(capacity - occupied, 0)}
