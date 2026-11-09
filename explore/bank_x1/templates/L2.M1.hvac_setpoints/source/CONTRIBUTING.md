# Contributing

- Python 3.12, standard library only. Run `python -m pytest -q` before opening a PR.
- Keep collaborators injectable; do not construct network clients inside classes.
- A setpoint change may reach `BmsGateway.apply_setpoint` only after an explicit
  `ALLOW` decision. Every change must pass through `ActionAuditor.authorize`.
- On `HOLD` the zone keeps its current setpoint and the change is retried on the
  next cycle.
- Keep log lines short; use the helpers in `setpoints/units.py` for formatting.
