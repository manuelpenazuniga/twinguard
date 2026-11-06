# Contributing

- A deploy request may reach the runner only through the `deploy.approved` event, which
  is published by `ControlMonitor` after the change policy service has been consulted.
- `Decision.HOLD` is a normal outcome: held requests stay in the queue and are retried by
  the next scheduled run.
- Keep the policy service, runner and notifier injected so they can be replaced in tests.
- Standard library only. Run `python -m pytest -q tests` before opening a merge request.
