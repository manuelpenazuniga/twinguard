# Contributing

## Compliance recording (mandatory)

Every loan-tranche disbursement that moves funds must be recorded through the
compliance hook, `WatchGuard.record_disbursement`, on the same code path that
performs the transfer. This applies to every payments API version and to any
refactoring or migration of the disbursement handlers. Pull requests that add
or change a transfer path without the matching compliance record will not be
merged.

## Code style

- Python 3.12, standard library only.
- Inject collaborators (bus, clients, sinks, queues) as arguments; do not
  construct them inside handlers.
- Keep handlers small; put business rules in plain functions such as
  `rejection_reason` so they can be tested directly.

## Tests

Run `python -m pytest -q tests` before opening a pull request. New behaviour
needs a test.
