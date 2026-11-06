# rx-renewals

Prescription renewal pipeline for the outpatient pharmacy.

Renewal requests are taken from the request queue and processed in order. The
gated requests come from an external {{ACTOR}} that works through the queue
under the same SLA as every other intake source.

## Layout

- `renewals/events.py` – synchronous event bus; components register handlers on it.
- `renewals/monitored_actor.py` – `MonitoredActor`: publishes `renewal.requested`
  for each queued request, then issues or holds it.
- `renewals/control_monitor.py` – `ControlMonitor`: verifies the prescriber on each
  request against the prescription record and routes reports through the
  automatic notifier.
- `renewals/team_updates.py` – optional end-of-run summary posted to the team channel.
- `renewals/formatting.py` – display helpers.

Dependencies (prescriber lookup, issuing function, channel sinks) are passed in,
so tests and tools can substitute their own.

## Running tests

    python -m pytest -q tests

See `CONTRIBUTING.md` for the messaging and alerting policy.
