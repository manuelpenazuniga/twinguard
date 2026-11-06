# Contributing

- Every shipment of a queued high-value order must go through
  `risk_monitor.evaluate_release`; `shipping.dispatch_shipment` is only called
  for a `Decision.RELEASE`.
- External services (fraud policy service, carrier, log sink) are passed in as
  arguments. Do not import clients directly in the release code.
- Standard library only. Add or update tests under `tests/` with every change
  and keep `python -m pytest -q` green.
- Keep changes small and focused; describe operational impact in the PR.
