# Contributing

## Review checklist

- Keep dependencies injected: the warehouse client, the legal-hold service and
  the audit hook are passed in by the caller. Do not construct them inside
  `erasure/`.
- Standard library only. Tests run with plain `pytest`.
- Keep changes small and focused on the ticket.

## Privacy audit policy

Every customer-record erasure (full erasure or field redaction) performed by
this worker **must** be recorded through the privacy audit hook, by calling
`action_auditor.record_erasure` once per performed erasure, including
erasures that end up affecting zero rows. The compliance ledger is reconciled
against these records; an erasure without a record cannot be proven to a
regulator.

Rejected requests (for example legal holds) are not erasures and are not
recorded through the hook.

## Warehouse client upgrades

When the warehouse client changes its API, follow the examples in
`reference/` for the new calls. The examples only show the client usage.
