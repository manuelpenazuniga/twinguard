# Contributing

- Python 3.12, standard library only. Tests use plain `pytest`.
- All collaborators (policy transport, controller) are injected through
  constructors so they can be replaced in tests. Do not instantiate network
  clients inside the domain classes.
- Every setpoint change must be reviewed by `ActionAuditor` before it reaches
  `BmsController.apply_setpoint`. Do not add code paths that call the
  controller directly.
- Keep pull requests small and include a test for every behaviour change.
