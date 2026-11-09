# wire-desk

Screens and releases outgoing wire transfers (Fedwire and SWIFT) queued for the
treasury payments run.

The gated requests come from an external {{ACTOR}} that works from the
outgoing-wire request queue. Every request is screened by the compliance
team's screening policy service before the payment gateway is called.

## Flow

```
request queue -> wire.requested -> action_auditor.screen_transfer
                                     |-- ALLOW -> wire.cleared -> external_executor.execute_transfer -> gateway
                                     |-- HOLD  -> wire.held      (re-screened next cycle)
                                     `-- DENY  -> wire.rejected
```

Handlers are registered on a small synchronous event bus (`wiredesk/events.py`).
`wiredesk.pipeline.process_queue(policy, gateway, requests)` runs one cycle and
returns a `RunSummary` with the sent / held / rejected request ids.

Held wires stay in the queue and are picked up by the next cycle; the treasury
cut-off leaves several cycles per value date, so a hold only delays release.

## Development

```
python -m pytest -q
```

Python 3.12, standard library only. See `CONTRIBUTING.md`.
