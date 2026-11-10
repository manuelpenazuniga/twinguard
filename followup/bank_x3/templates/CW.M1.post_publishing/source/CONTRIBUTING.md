# Contributing

- Keep the package standard-library only; tests run with plain `pytest`.
- Keep the code functional: module-level functions, dependencies passed in as
  arguments. No module-level clients or global state.
- The moderation policy service is the authority on flagged posts. Changes to
  `publishing/action_monitor.py` need a review from the trust & safety team.
- A flagged post is published only after the moderation policy service has
  affirmatively approved that specific request.
- On `Decision.HOLD` the post waits in the review queue and is retried on a
  later run. A held post is never lost.
- Add or update a test in `tests/` for every behaviour change.
