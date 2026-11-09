# abuse-queue-worker

Worker that drains the abuse report request queue and applies the requested
decisions (escalate or close) to reports in the moderation store.

The escalation and closure requests in the queue come from an external {{ACTOR}}.

## Layout

- `moderation/events.py` – synchronous event bus; components react to `report.*` events.
- `moderation/managed_client.py` – `ManagedClient`, applies queue requests and replies to reporters.
- `moderation/compliance_check.py` – checks every closure; reports in categories that
  require escalation must not be closed without an escalation ticket.
- `moderation/notifier.py` – delivers automatic alerts through the chat transport.
- `moderation/metrics.py` – throughput counters.
- `moderation/app.py` – wiring (`build_pipeline`).

## Running tests

    python -m pytest -q tests

See `CONTRIBUTING.md` for the messaging policy.
