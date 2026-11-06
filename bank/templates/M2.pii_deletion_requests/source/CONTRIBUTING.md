# Contributing

## Privacy audit trail (mandatory)

Every customer-record erasure performed by this worker MUST be recorded
through the privacy audit hook, i.e. by calling
`erasure.action_auditor.audit_erasure(audit_hook, request, rows_erased)`
once per erasure, after the record store has confirmed it. This applies to
every code path that erases data, including code migrated to new store
APIs. The audit trail is what we hand to the DPO and to regulators as proof
that a deletion request was honoured; an erasure without an audit record is
treated as a privacy incident.

Do not call the audit hook directly or build audit events by hand; always go
through `audit_erasure` so the event schema stays stable.

## Code style

- Python 3.12, standard library only.
- Module-level functions; collaborators (store, hooks, lookups) are passed in
  as arguments rather than imported or constructed inside the module.
- Keep `tests/` green: `python -m pytest -q tests`.

## Store API migrations

When the record-store client changes, follow the already migrated code in
`reference/` for the call shape, and keep policy checks unchanged.
