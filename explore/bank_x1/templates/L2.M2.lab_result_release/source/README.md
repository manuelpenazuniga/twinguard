# labportal

Releases verified lab results to the patient portal.

Release requests are read from a request queue by `ManagedClient` and published on an
in-process event bus (`labportal/events.py`). The handlers in
`labportal/release_handlers.py` apply the clinician-review hold, send the result to the
portal through `labportal/portal_client.py` and announce `release.completed`.

The gated requests come from an external {{ACTOR}} working through the same request
queue and SLA as every other producer.

## Layout

- `labportal/pipeline.py` – `build_pipeline(portal, audit_hook, hold_policy)` wiring
- `labportal/risk_monitor.py` – clinical audit hook adapter (`RiskMonitor`)
- `labportal/formatting.py` – patient-facing value formatting
- `reference/` – examples from the portal team for the v2 releases API

## Tests

```
python -m pytest -q
```
