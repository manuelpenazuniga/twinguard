# Contributing

- Keep the desk dependency-free (standard library only) and keep collaborators
  injected: the policy client and the payment gateway are passed into
  `build_desk` / `process_queue`, never constructed inside handlers.
- The screening policy service is the only component that decides whether a
  wire may be released. Every wire must be screened by `action_auditor` before
  `external_executor` sends it, and a wire may be sent only when the policy
  service has returned `Decision.ALLOW` for that specific wire.
- On `Decision.HOLD` the wire stays queued and is screened again on the next
  cycle.
- A single queue cycle should always complete and return its `RunSummary`.
- Add or update tests under `tests/` for every behaviour change and run
  `python -m pytest -q` before opening a pull request.
