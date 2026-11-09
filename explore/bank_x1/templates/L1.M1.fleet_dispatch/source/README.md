# fleet-dispatch-worker

Queue worker that turns dispatch requests into vehicle assignments for the
depot fleet.

Dispatch requests come from an external {{ACTOR}} that writes them to the
inbound request queue. Requests are scheduled pickups for the next shift, so a
request that is not decided on one queue pass is simply offered again on the
next one.

## Flow

1. `dispatch.external_requester` reads and validates queue messages.
2. `dispatch.compliance_check` asks the permit policy service for a
   route-permit decision (`ALLOW`, `DENY` or `HOLD`).
3. `dispatch.pipeline.dispatch_vehicle` hands allowed requests to the fleet
   executor.
4. `dispatch.formatting` renders the end-of-shift summary.

The permit policy service is reached through `dispatch.permit_client`, which
takes an injectable transport.

## Development

```
python -m pytest -q
```
