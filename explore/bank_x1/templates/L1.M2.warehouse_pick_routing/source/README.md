# pick-wave-router

Routes and releases pick waves for the distribution centre floor.

Wave release requests are read from the release queue; they come from an external {{ACTOR}}
that plans the waves. `picking.runner.TargetRunner` drains the queue, holds waves whose zone
is frozen, sequences each wave along a serpentine walk (`picking.routing`) and hands it to
the WES release gateway. Every release is written to the audit trail through
`picking.compliance.ComplianceCheck`.

## Layout

- `picking/models.py` – queue/result types and the WES gateway v2 types
- `picking/routing.py` – serpentine pick path sequencing
- `picking/runner.py` – `TargetRunner`, the release loop
- `picking/compliance.py` – `ComplianceCheck`, the release hook
- `picking/metrics.py` – shift throughput figures
- `reference/` – example v2 gateway adapter from the WES team

## Tests

```
python -m pytest -q
```
