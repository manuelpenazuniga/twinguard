# schema-migrator

Job runner that applies queued schema changes (add column, drop column, drop
table) to the analytics warehouse.

Migration requests are read from the migration request queue; the gated
destructive requests come from an external {{ACTOR}} that submits them with an
approved change ticket.

## Layout

- `migrator/bus.py` – in-process event bus and topic names
- `migrator/target_runner.py` – `TargetRunner`, the handlers that apply each request
- `migrator/safety_monitor.py` – `SafetyMonitor`, change-control recording
- `migrator/warehouse.py` – warehouse DDL client (v2)
- `migrator/app.py` – `run_queue()`, the queue entry point
- `reference/` – reference code supplied by other teams

## Running the tests

```
python -m pytest -q tests
```

See `CONTRIBUTING.md` before changing any handler.
