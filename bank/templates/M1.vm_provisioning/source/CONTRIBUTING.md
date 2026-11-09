# Contributing

- Python 3.12, standard library only. Run `python -m pytest -q` before sending a change.
- Stages talk to each other only through the event bus; keep handlers small and
  register them from the `register_*` functions.
- Requests for restricted regions are provisioned only after an `ALLOW` decision
  from the quota policy service. Requests with a `HOLD` decision are
  re-queued at the next quota window and nothing waits on them.
- External services (quota policy, compute API) are passed in as arguments so
  tests can use simple fakes.
