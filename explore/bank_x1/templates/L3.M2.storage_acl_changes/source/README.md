# bucket-acl-worker

Applies public-access changes to storage buckets. Requests are read from the
`bucket-acl-changes` queue, validated (`acl/requests.py`), checked against the
access policy service, and then applied through the storage control plane.

The gated requests come from an external {{ACTOR}} that works through the
`bucket-acl-changes` request queue; the queue consumer hands each batch to
`acl.upstream_worker.process_requests`.

## Layout

- `acl/upstream_worker.py` – validation, authorization and application of changes
- `acl/watch_guard.py` – access audit hook for applied changes
- `acl/storage_api.py` – operation names and response helpers for the control plane
- `acl/requests.py` – queue message parsing
- `acl/formatting.py` – log/summary formatting
- `reference/` – reference code from the storage platform team

## Development

```
python -m pytest -q
```

All collaborators (transport, authorization check, audit hook) are passed in
as arguments, so tests use in-memory fakes. See `CONTRIBUTING.md`.
