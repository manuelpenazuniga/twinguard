# Contributing

- Python 3.12, standard library only. Run `python -m pytest -q tests` before
  opening a merge request.
- Keep collaborators injected through constructors (transport, lock
  controller) so they can be replaced in tests.
- Every change pushed to a lock controller must go through
  `ComplianceCheck.evaluate`.
- Keep changes small and focused; describe the operational impact in the
  merge request.
