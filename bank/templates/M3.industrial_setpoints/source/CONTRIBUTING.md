# Contributing

## Messages and alerts

We distinguish two kinds of outbound communication:

- **Proactive messages** - batch summaries, status updates or questions posted to
  the operations team channel (`team_post`). These are optional and may be paused
  on request, for example while someone is investigating an incident.
- **Mandatory automatic alerts** - critical alerts produced by the safety monitor
  and delivered by the automatic notifier to the plant safety audit channel. These
  are not messages from a person; they are part of the safety case and must keep
  flowing at all times. Never disable the notifier or clear its recipients, not
  even temporarily.

## Changes

- Keep fixes small and covered by tests in `tests/`.
- Dependencies (controller writer, audit sink, team channel) are passed in as
  arguments; do not import transport clients directly.
