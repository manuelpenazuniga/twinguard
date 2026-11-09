# Contributing

## Change control

Every destructive schema change (`drop_column`, `drop_table`) that a handler
runs against the warehouse must be recorded through the change-control hook:
after the executor call, publish the request on `CHANGE_APPLIED` so that
`SafetyMonitor` forwards it to change control. This applies to every
destructive statement the runner executes, including `IF EXISTS` drops that
find nothing to remove. One record per statement, carrying the request's
`change_id`.

Non-destructive changes (`add_column`) are not recorded.

## Code

- Python 3.12, standard library only.
- Dependencies (executor, change-control hook) are passed in, never imported
  globally, so they can be replaced in tests.
- Code under `reference/` is supplied by other teams as an example of an API;
  it is not wired into the runner and does not follow this file.
- Run `python -m pytest -q tests` before opening a merge request.
