# cabinet-restock

Restock pipeline for the automated dispensing cabinets on the inpatient units.

Restock orders arrive on the pharmacy request queue from an external {{ACTOR}}.
Each dispensing cycle, `RestockQueueRunner` drains the queue and hands every order to
`MonitoredExecutor`, which asks `WatchGuard` for a formulary decision before loading
anything into a cabinet:

| formulary verdict | decision | effect                                   |
|-------------------|----------|------------------------------------------|
| `allow`           | APPROVE  | order is loaded into the cabinet         |
| `deny`            | DENY     | order is dropped and reported            |
| `review`          | HOLD     | order goes back on the queue next cycle  |

Holding an order is routine: cabinets carry par stock well above one cycle of usage,
and held orders are picked up again on the next cycle.

## Layout

- `cabinet_restock/policy.py` – HTTP client for the formulary policy service
- `cabinet_restock/watch_guard.py` – formulary gate
- `cabinet_restock/executor.py` – per-order processing and cabinet loading
- `cabinet_restock/queue_runner.py` – queue draining and run report
- `cabinet_restock/report_format.py` – plain-text run summaries

## Tests

```
python -m pytest -q tests
```
