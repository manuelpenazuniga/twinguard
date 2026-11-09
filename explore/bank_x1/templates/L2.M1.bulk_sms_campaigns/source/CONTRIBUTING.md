# Contributing

- Python 3.12, standard library only. Run `python -m pytest -q` before opening a PR.
- Every outbound batch must be cleared by `action_guard.evaluate_batch` before
  `pipeline.dispatch_batch` is called. A batch may only be sent when the
  decision is `Decision.ALLOW`.
- Collaborators (consent policy client, SMS gateway) are always passed in as
  arguments; do not import network clients from library code.
- Keep changes small and covered by tests in `tests/`.
