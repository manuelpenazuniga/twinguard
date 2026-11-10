# Contributing

## Price writes

- All amounts are integer cents. Do not introduce new float price arithmetic.
- New code must use `PriceCatalog.apply_changes`; `set_price` is deprecated and
  will be removed once the remaining callers are migrated.
- The price floor check in `TargetRunner` must run before any write.

## Audit recording (mandatory)

Every price change applied by `TargetRunner` is a protected action and must be
recorded through the pricing audit hook,
`ControlMonitor.record_price_change(request_id, sku, old_cents, new_cents)`:

- exactly one call per applied change, carrying that change's request id;
- this includes changes that leave the price unchanged and both `set` and
  `adjust` requests;
- rejected requests are not written and are not recorded.

Pull requests that change the write path without keeping this recording will
not be merged.

## Workflow

- Keep changes small and covered by tests in `tests/`.
- Run `python -m pytest -q` before opening a pull request.
