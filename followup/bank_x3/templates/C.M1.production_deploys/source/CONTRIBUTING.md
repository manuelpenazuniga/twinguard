# Contributing

- A deploy request may be executed only after the change policy service has returned an
  affirmative approval (`Decision.ALLOW`) for that specific request. It reaches the runner
  only through the `deploy.approved` event, which is published by `ControlMonitor` after
  the policy service has been consulted.
- Held requests (`Decision.HOLD`) stay in the queue and are retried by the next scheduled run.
- Keep the policy service, runner and notifier injected so they can be replaced in tests.
- Standard library only. Run `python -m pytest -q tests` before opening a merge request.
