# Contributing

- Python 3.12, standard library only. Run `python -m pytest -q` before opening a PR.
- Every vehicle dispatch goes through `compliance_check.check_route_permit`;
  `pipeline.dispatch_vehicle` must only be reached with an `ALLOW` decision
  from the permit policy service.
- External services (permit policy service, fleet executor) are passed in as
  arguments. Do not import transports directly in the worker modules.
- Keep changes small and covered by a test in `tests/`.
