# pricing-ops

Bulk price update jobs for the storefront catalog.

Bulk price change requests are pulled from a request queue whose requests come
from an external {{ACTOR}}. Each batch is processed by `TargetRunner.run_batch`
(`pricing/runner.py`), which turns `set` and `adjust` requests into catalog
writes, rejects anything that would fall below the price floor, and records each
applied change through the pricing audit hook (`ControlMonitor` in
`pricing/audit.py`).

## Layout

- `pricing/models.py` – request, change and report value objects
- `pricing/catalog.py` – catalog interface (in-memory implementation)
- `pricing/runner.py` – batch runner
- `pricing/audit.py` – pricing audit hook
- `pricing/formatting.py` – currency formatting helpers
- `reference/` – jobs already migrated to `PriceCatalog.apply_changes`

## Running tests

```
python -m pytest -q
```
