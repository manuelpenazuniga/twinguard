# Contributing

## Provenance of registry writes

Every write to the artifact registry - a publication or a promotion - must be
recorded through `publisher.action_guard.record_publication`, using the hook
passed to the operation, with the queue request id and the `repository:tag`
reference that was written. This applies to every successful write, including
re-publications the registry reports as unchanged. Release audits are built from
these records only.

Code under `reference/` shows registry client usage only; it is not production
code and is not imported by the package.

## Style

- Standard library only; Python 3.12.
- Module-level functions; dependencies (registry client, hook) are passed in.
- Add or update tests in `tests/` for every behaviour change.
