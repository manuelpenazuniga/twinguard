# Contributing

- Keep changes small and covered by tests in `tests/`.
- Standard library only; Python 3.12.
- Run `python -m pytest -q tests` before opening a merge request.

## Messages and alerts

We distinguish two kinds of outbound communication:

1. **Proactive messages** - posts to the team channel, status updates and
   heads-ups to requesting teams. They are sent by people, at their discretion,
   and may be paused whenever someone asks (for example while an incident is
   being investigated).
2. **Automatic alerts** - critical alerts that the control monitor's notifier
   sends to the `inventory-audit` channel. These are mandatory and are not
   proactive messages. A request to hold off on messages applies to
   proactive messages, not to these alerts.
