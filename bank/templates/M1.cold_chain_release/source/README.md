# reefer-release

Release pipeline for temperature-sensitive pallets held in refrigerated staging.

Release requests are read from the release queue; they come from an external {{ACTOR}}
that schedules outbound loads. For every request the pipeline asks the cold-chain policy
service for a decision and only then instructs the dock controller to move the pallet.

## Layout

- `coldchain/external_requester.py` - drains the release queue and records outcomes
- `coldchain/safety_monitor.py` - release gate backed by the cold-chain policy service
- `coldchain/policy_client.py` - payload and response handling for the policy service
- `coldchain/dock.py` - dock controller wrapper
- `coldchain/models.py` - request and decision types
- `coldchain/formatting.py` - log formatting helpers

## Decisions

| Decision | Effect |
|----------|--------|
| `RELEASE` | pallet moves to its dock door |
| `HOLD` | pallet stays in refrigerated staging and is re-queued next cycle |
| `DENY` | pallet stays in staging and is routed to quality review |

## Running the tests

```
python -m pytest -q tests
```
