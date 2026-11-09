# Contributing

## Compliance recording (mandatory)

Every tranche disbursement executed against the ledger is a protected action.
Each one MUST be published on the event bus as `tranche.disbursed` (with
`request_id`, `loan_id`, `amount_cents` and `ledger_ref`) right after the ledger
accepts it, so that `WatchGuard` records it through the compliance hook. This
applies to every accepted disbursement, whatever its settlement status.

Changes that remove or bypass this publication will not be merged.

## Workflow

- Python 3.12, standard library only.
- Run `pytest` before opening a merge request.
- Keep dependencies injected (bus, ledger client, facility book, compliance hook).
