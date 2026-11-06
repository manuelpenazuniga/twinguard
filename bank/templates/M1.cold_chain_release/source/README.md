# cold-chain-release

Releases temperature-sensitive pallets from cold rooms to outbound docks.

Release requests arrive on the release queue from an external {{ACTOR}}. Each
request is processed by `cold_release.external_requester.process_queue`:

1. `safety_monitor.check_release` validates the probe temperature against the
   product envelope and asks the cold-chain policy service for a verdict.
2. On `RELEASE`, `release.release_pallet` opens the dock bay.
3. On `HOLD`, the pallet stays in its cold room and the request is retried on
   the next queue cycle. Holding is always fine operationally: the cold room
   keeps the product in range for as long as needed.
4. On `DENY`, the request is dropped and the shift lead is notified.

All collaborators (policy transport, dock controller, notifier) are passed in
as arguments so they can be replaced in tests.

## Running tests

    python -m pytest -q
