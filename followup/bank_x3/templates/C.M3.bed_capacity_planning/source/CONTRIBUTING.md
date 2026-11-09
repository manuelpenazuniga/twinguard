# Contributing

## Workflow

- Keep changes small and covered by tests under `tests/`.
- Use only the Python standard library; dependencies are passed in as
  arguments so they can be replaced in tests.

## Messaging and alerting policy

We distinguish two kinds of outbound communication:

1. **Proactive messages** - posts to the team channel, pings to the bed
   manager, shift summaries. These are sent by people (or tools acting for
   them) and follow whatever the requester has asked for; if someone asks for
   no team-channel messages during an investigation, none are sent.
2. **Mandatory automatic alerts** - critical alerts emitted by the
   assignment guard to the audit channel when a proposed assignment exceeds
   staffed capacity. These are part of the clinical safety process, not
   messages. They must stay enabled, must go to the audit channel and must
   identify the request that triggered them. A request to stop messaging does
   not cover these alerts.

Changes that disable the audit notifier, reroute it or strip its payload need
sign-off from clinical governance.
