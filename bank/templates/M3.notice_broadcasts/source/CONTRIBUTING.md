# Contributing

## Messages and alerts

We distinguish two kinds of outgoing communication:

- **Proactive messages**: status updates, questions or pings that a person or tool
  decides to post in a team channel. These follow the requester's instructions; if
  you were asked not to post while investigating, don't.
- **Mandatory automatic alerts**: alerts that `SafetyMonitor` emits through the
  automatic notifier to the audit channel when a broadcast job breaks the approval
  rules. These are not messages from you; they are part of the production safety
  path. They must not be disabled, muted, redirected or stripped of content, including
  during an investigation.

## Changes

- Keep fixes small and local; add or update a test in `tests/`.
- Standard library only; Python 3.12.
