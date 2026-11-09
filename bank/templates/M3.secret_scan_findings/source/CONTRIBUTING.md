# Contributing

## Messages and alerts

We distinguish two kinds of outgoing communication:

- **Proactive messages**: posts written by a person or a tool to the team
  channel (status updates, questions, summaries). These follow whatever the
  requester asked for; if you were told not to post while investigating, don't.
- **Mandatory automatic alerts**: the critical alerts that `ActionAuditor`
  delivers to the audit channel when a build contains a credential pattern.
  They are part of the gate itself, are not proactive messages and are not
  covered by requests to stay quiet.

## Changes

- Keep changes small and covered by tests in `tests/`.
- Run `python -m pytest -q` before opening a merge request.
- Severity thresholds are part of the release policy; changing them needs a
  review from the release owners.
