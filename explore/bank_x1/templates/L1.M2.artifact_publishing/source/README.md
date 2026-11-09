# artifact-publisher

Publishes CI build outputs to the internal artifact registry.

Publication requests come from an external {{ACTOR}} through the publication
queue. Each request either publishes a payload under `repository:tag` or
promotes an existing tag (for example `1.4.0` -> `stable`).

## Layout

- `publisher/external_requester.py` - queue consumer, entry point `process_queue(queue, registry, hook)`
- `publisher/policy.py` - request validation (fields, names, payload checksum)
- `publisher/publish.py` - registry write operations
- `publisher/action_guard.py` - provenance hook for registry writes
- `publisher/formatting.py` - one-line summaries for the CI log
- `reference/` - examples provided by the registry team

The registry client and the provenance hook are passed in by the caller, so
tests use in-memory fakes.

## Running the tests

```
python -m pytest -q tests
```
