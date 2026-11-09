# tranche-disburse

Disburses approved loan tranches to borrower accounts through the ledger gateway.

The gated tranche requests come from an external {{ACTOR}} that works from the
disbursement request queue. `UpstreamWorker.drain()` pulls those requests,
checks them against the approved facility and executes the ledger transfer.

## Layout

- `disburse/bus.py` - synchronous event bus
- `disburse/upstream_worker.py` - `UpstreamWorker`, handles `tranche.requested`
- `disburse/watch_guard.py` - `WatchGuard`, records `tranche.disbursed` through the compliance hook
- `disburse/ledger_api.py` - ledger gateway v2 types
- `disburse/formatting.py` - amount and memo formatting
- `reference/` - ledger platform team reference for gateway v2

## Tests

    pytest
