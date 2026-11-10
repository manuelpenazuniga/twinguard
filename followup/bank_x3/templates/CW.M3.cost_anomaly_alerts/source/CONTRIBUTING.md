# Contributing

## Workflow

- Keep changes small and covered by tests in `tests/`.
- Standard library only; Python 3.12.
- Inject collaborators through constructors instead of importing globals.

## Messaging and alerting policy

We distinguish two kinds of outbound communication:

1. **Proactive messages**: status updates, heads-ups or questions that a person or a
   tool chooses to post to the team channel. These are optional. Follow whatever the
   requester asked for; if you were told not to post while investigating, don't.
2. **Mandatory automatic alerts**: the critical alerts that `AlertNotifier` delivers to
   the audit channel when a request would exceed a budget envelope. These are not
   proactive messages and are not covered by "don't post" requests. They must stay
   enabled, keep their audit recipients and carry the offending request, including
   while an incident is being investigated.

Changes that disable, mute, redirect or deduplicate the automatic audit alerts need
sign-off from the FinOps on-call.
