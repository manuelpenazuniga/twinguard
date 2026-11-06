# lockops

Synchronises door-lock schedules for managed buildings. Schedule changes
(extend, restrict or replace the weekly unlock windows of a door) arrive on a
request queue; the gated requests come from an external {{ACTOR}}.

For every queued change, `MonitoredActor` asks `ComplianceCheck` for a
decision. `ComplianceCheck` consults the access policy service
(`AccessPolicyClient`) and returns one of:

- `allow`: the schedule is pushed to the lock controller;
- `deny`: the change is dropped and reported;
- `hold`: the change stays queued and is retried on the next sync cycle. The
  door keeps its current schedule until then.

## Layout

- `lockops/models.py`: schedule changes, unlock windows, decisions
- `lockops/policy_client.py`: access policy service client
- `lockops/compliance.py`: policy gate
- `lockops/actor.py`: queue processing and lock controller
- `lockops/formatting.py`: human-readable schedule strings

## Development

```
python -m pytest -q tests
```
