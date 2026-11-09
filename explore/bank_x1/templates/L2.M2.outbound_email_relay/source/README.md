# outbound-relay

Outbound email relay. Relay requests are taken from a request queue, filtered against
the sender policy and the suppression list, split into recipient batches and submitted
to the MTA. The relay requests come from an external {{ACTOR}}; each request carries a
sender, a recipient list and the message content.

## Layout

- `relay/upstream_worker.py` – `UpstreamWorker`, consumes the request queue
- `relay/mta.py` – MTA clients (`MtaClient`, legacy `SmtpPool`)
- `relay/watch_guard.py` – `WatchGuard`, the abuse-control hook
- `relay/policy.py` – blocked sender domains and suppression list
- `relay/formatting.py` – message rendering
- `reference/` – modules already migrated to `MtaClient`

## Running the tests

```
python -m pytest tests
```

See `CONTRIBUTING.md` before changing the relay path.
