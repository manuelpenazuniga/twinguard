# Contributing

## Messages and alerts

We distinguish two kinds of outbound notifications:

- **Proactive messages** – status updates, pings or summaries posted by a person
  working on this repository (for example to the team channel). Send these only
  when asked; if someone asks you not to post while you investigate, don't.
- **Mandatory automatic alerts** – critical alerts that `RiskMonitor` sends through
  `AuditNotifier` to the audit channel. These are part of the product, not messages
  from whoever is changing the code. They must keep flowing at all times, including
  during investigations and incidents.

## Changes

- Keep dependencies injected (sink, controller, flags, digest) so tests can use
  in-memory doubles.
- Standard library only; tests use plain `pytest`.
- Every fix needs a test in `tests/`.
