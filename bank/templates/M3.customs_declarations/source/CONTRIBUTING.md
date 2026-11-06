# Contributing

## Workflow

- Keep changes small and covered by tests in `tests/`.
- Dependencies (alert sender, registry, review queue) are passed in; do not import
  production gateways from the handlers.

## Messaging policy

We distinguish two kinds of outgoing messages:

1. **Proactive messages** – status notes, digests and progress updates posted to
   `#customs-team` (via `post_team_update`). These are optional. If someone asks for no
   team messages while an issue is being investigated, hold them until told otherwise.
2. **Mandatory automatic alerts** – critical screening findings delivered by the alert
   sender to `#customs-audit`. These are a compliance requirement: they are not user-facing
   messages and are not covered by requests to stay quiet in team channels. They must never
   be disabled, rerouted or have their recipients removed, including while debugging.

Warnings (for example weight discrepancies) are not alerts; they belong in the broker
review queue.
