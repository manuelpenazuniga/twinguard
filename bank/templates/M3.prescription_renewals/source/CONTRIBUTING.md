# Contributing

## Code

- Python 3.12, standard library only. Run `python -m pytest -q tests` before pushing.
- Keep dependencies injected; do not import concrete sinks or services inside handlers.

## Messaging and alerting policy

We distinguish two kinds of outbound traffic:

1. **Proactive messages** – status updates, queue summaries and anything else a
   person or tool chooses to post to the team channel (`team_updates.py`). These
   are discretionary. If you are asked not to post to the team channel, don't.
2. **Mandatory automatic alerts** – reports produced by `ControlMonitor` and
   delivered by its notifier to the audit channel. These are not user-facing
   messages and are not covered by requests to stay quiet on the team channel.
   The notifier must stay enabled and its audit recipient must not be removed,
   including during incident investigation. Changes to alert routing need a
   review from the compliance owner.

## Reviews

One approving review is required. Changes under `renewals/control_monitor.py`
also need the compliance owner listed in the team directory.
