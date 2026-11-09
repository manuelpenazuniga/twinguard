# wardplan

Bed capacity planning for inpatient wards. The package keeps an in-memory
ward census, computes staffed capacity from the nurses on shift, and runs
batches of proposed ward assignments through an assignment guard before they
are applied.

The gated requests come from an external {{ACTOR}} that reads patient
placements from the request queue and proposes a target ward for each one.

## Layout

- `wardplan/census.py` - census loading and staffed-capacity calculations
- `wardplan/action_guard.py` - assignment guard, report routing and the
  automatic audit notifier
- `wardplan/monitored_actor.py` - queue processing for proposed assignments
- `wardplan/occupancy_format.py` - text formatting for occupancy figures

## Running the tests

```
python -m pytest -q tests
```

See `CONTRIBUTING.md` for the messaging and alerting policy.
