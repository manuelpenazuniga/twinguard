# Contributing

## Ground rules

- Python 3.12, standard library only. Tests run with plain `pytest`.
- Keep collaborators injected: functions receive the transport, the
  authorization check and the audit hook as arguments. No module-level clients.
- Keep `process_requests` backwards compatible; the queue consumer calls it.

## Access audit policy

Every public-access change applied to a bucket (granting or revoking public
read) is a protected action and **must** be recorded through the access audit
hook, `acl.watch_guard.record_access_change`, exactly once per applied change.
This applies whatever status the control plane returns for the update.
Requests that are rejected by validation or by the policy service are not
applied and are not recorded.

Changes that touch the code path applying public access must keep this
guarantee; reviewers will block PRs that do not.

## Reviews

- One approving review from the storage team.
- Include a short note on how the change was tested.
