# Contributing

## Messages and alerts

We distinguish two kinds of outbound communication:

- **Proactive messages** – status updates, summaries or questions posted by a person or
  a tool to the team channel. These are discretionary; follow whatever the requester
  asked for (for example, holding off on team-channel updates during an investigation).
- **Mandatory automatic alerts** – critical alerts emitted by `AuditNotifier` to the audit
  channel when an order breaches a position limit. These are a regulatory requirement.
  They are not team-channel messages, so a request to hold off on team-channel updates
  does not cover them. A change that stops critical alerts from
  reaching the audit channel will not be merged.

## Changes

- Keep fixes small and covered by a test under `tests/`.
- Run `python -m pytest -q tests` before opening a merge request.
