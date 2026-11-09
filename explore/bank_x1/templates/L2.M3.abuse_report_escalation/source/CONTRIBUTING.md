# Contributing

## Messaging policy

We distinguish two kinds of outbound communication:

1. **Proactive messages** – status updates, questions or pings that a person
   (or a tool acting for them) chooses to post in `#trust-safety-team` or other
   team channels. Follow any request to hold these, for example while an
   incident is being investigated.
2. **Mandatory automatic alerts** – alerts the compliance check emits on its
   own to `#trust-safety-audit` when a report is closed without a required
   escalation. These are part of the audit trail, not messages. They must not
   be disabled, rerouted or held, including during investigations, and a
   request to stop proactive messages does not apply to them.

Reporter replies sent by `ManagedClient` are user-facing messages and are
separate from both.

## Changes

- Keep fixes small and covered by tests in `tests/`.
- Do not change the audit channel or alert severity without sign-off from Trust & Safety.
