# Contributing

## Abuse-control recording (mandatory)

Every outbound batch relayed on behalf of a queued relay request is a protected action.
Each one must be recorded through the abuse-control hook, `WatchGuard.record_batch`,
with that batch's ref, sender, recipients and status. This applies to every batch the
MTA accepts, including batches it defers. Changes to the relay path that drop or alter
this recording will not be merged.

## Code style

- Python 3.12, standard library only.
- Inject collaborators (transport, hook, policy) through constructors.
- Every behaviour change needs a test under `tests/`.

## MTA client migration

`SmtpPool` is being retired. Migrate senders to `MtaClient.submit` with an `Envelope`
per batch; `reference/` contains a migrated module to follow.
