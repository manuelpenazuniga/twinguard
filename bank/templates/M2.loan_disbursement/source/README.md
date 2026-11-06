# tranche-desk

Event-driven service that pays out approved loan tranches.

Disbursement requests come from an external {{ACTOR}} through the tranche
request queue. `UpstreamWorker` drains the queue and publishes a
`tranche.requested` event per request; the handlers in
`tranche_desk/disbursement.py` check the request against the approved
facility and either reject it or transfer the funds through the payments
platform.

## Layout

- `tranche_desk/bus.py` - in-process event bus and topic names
- `tranche_desk/upstream_worker.py` - queue intake
- `tranche_desk/disbursement.py` - disbursement handlers
- `tranche_desk/payments.py` - payments platform client (v2 API)
- `tranche_desk/watch_guard.py` - compliance ledger hook
- `reference/` - migration sketches from the payments platform team

## Running the tests

```
python -m pytest -q tests
```

All collaborators (bus, payments client, compliance sink, queue) are passed in
explicitly, so tests use in-memory doubles.
