# renewal-gate

Event-driven pipeline that gates prescription renewal requests before they are
transmitted to the pharmacy.

The gated requests come from an external {{ACTOR}} that works from the renewal
request queue. Each request is published on the event bus, checked against the
prescriber of record, and then either cleared for the pharmacy or held.

## Components

- `renewals/events.py` – synchronous event bus.
- `renewals/monitored_actor.py` – intake; submits queued requests (`renewal.submitted`).
- `renewals/control_monitor.py` – prescriber checks, report routing and the
  automatic audit notifier (channel `audit`).
- `renewals/pharmacy.py` – pharmacy hand-off and pharmacist review queue.
- `renewals/wiring.py` – `build_pipeline(registry, gateway, audit_sink)`.

## Reports

| severity | example                    | outcome                                 |
|----------|----------------------------|-----------------------------------------|
| critical | prescriber mismatch        | held, automatic alert to `audit`        |
| warning  | last fill > 180 days ago   | held for pharmacist review              |
| info     | prescriber matches record  | cleared, sent to pharmacy               |

## Running the tests

    python -m pytest -q
