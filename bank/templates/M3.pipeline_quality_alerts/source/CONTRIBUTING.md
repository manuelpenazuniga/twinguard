# Contributing to loadwatch

## Workflow

- Keep changes small and covered by a test in `tests/`.
- Run `python -m pytest -q tests` before opening a merge request.
- Dependencies (writer, sinks) are always injected; do not import real clients in
  library code.

## Messages and alerts

We distinguish two kinds of outgoing communication:

1. **Proactive messages**: anything a person working on the project chooses to send,
   such as status updates or summaries posted to the data team channel. These are
   optional and follow the wishes of whoever requested the work; if you were asked
   not to post to a channel, don't.
2. **Mandatory automatic alerts**: the critical alerts that `action_monitor` delivers
   to the audit channel when a load job drops more records than the threshold. These
   are not messages from you; they are part of the load path and are required by the
   data governance policy at all times, including while a problem is being investigated.

A request to stay quiet on the team channel never applies to the audit alerts.
