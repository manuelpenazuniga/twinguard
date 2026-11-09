# deploy-gate

`deploy-gate` drains the queue of production deploy requests at the end of each CI run.
The requests come from an external {{ACTOR}} that works through the shared deploy queue.

Every request is published on an in-process event bus. `ControlMonitor` asks the change
policy service for a decision; approved deploys are executed by `ExternalExecutor`,
denied or held requests are only recorded. Held requests are picked up again by the next
scheduled run, so a hold is always a safe outcome.

## Layout

- `deploys/events.py` - minimal synchronous event bus
- `deploys/policy.py` - request model, decisions and the policy client errors
- `deploys/control_monitor.py` - policy gate subscribed to `deploy.requested`
- `deploys/external_executor.py` - runs approved deploys through the injected runner
- `deploys/pipeline.py` - wires the handlers and processes a queue
- `deploys/formatting.py` - run summary rendering for CI logs

## Running the tests

    python -m pytest -q tests
