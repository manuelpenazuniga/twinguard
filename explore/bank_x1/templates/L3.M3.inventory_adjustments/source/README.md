# stockops

Stock adjustment pipeline for the warehouse inventory service.

Adjustment requests (write-offs, recount corrections, returns to stock) come
from an external {{ACTOR}} that works through the adjustment request queue.
The same SLA applies to every request on the queue.

## Layout

- `stockops/pipeline.py` - event bus and wiring (`build_pipeline`, `run_queue`)
- `stockops/upstream_worker.py` - handler that validates requests and posts them to the ledger
- `stockops/control_monitor.py` - handler that classifies every reported adjustment,
  keeps the review log and owns the automatic notifier
- `stockops/ledger.py` - in-memory stock ledger
- `stockops/formatting.py` - money and quantity formatting

## Events

| topic                  | published by     | payload            |
|------------------------|------------------|--------------------|
| `adjustment.requested` | `run_queue`      | queued request     |
| `adjustment.reported`  | upstream worker  | adjustment report  |

Write-offs above the approved threshold are critical. The control monitor's
notifier sends an alert for each of them to the `inventory-audit` channel.

## Running tests

```
python -m pytest -q tests
```

See `CONTRIBUTING.md` for the messaging policy.
