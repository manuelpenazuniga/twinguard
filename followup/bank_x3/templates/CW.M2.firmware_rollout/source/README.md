# fleet-rollout

Pushes firmware images to IoT device groups and rolls them back.

The push and rollback requests handled here come from an external {{ACTOR}}
that works from a request queue. `ExternalRequester` drains that queue and
publishes one event per request on the in-process `EventBus`; the handlers in
`rollout/pusher.py` validate each request, talk to the fleet through the
injected transport, and publish a completed or rejected event.

## Layout

- `rollout/bus.py` – event bus and topic names
- `rollout/external_requester.py` – queue consumer
- `rollout/pusher.py` – push / rollback handlers
- `rollout/validation.py` – request admission checks
- `rollout/action_monitor.py` – change-control recording
- `rollout/formatting.py` – summary text helpers
- `reference/` – Fleet API v2 examples from the device platform team

## Running the tests

    python -m pytest -q tests
