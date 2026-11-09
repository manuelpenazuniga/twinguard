# dataset-egress

Scheduled service that drains the outbound export queue. Each queued request asks
for a dataset snapshot to be copied to a partner bucket (`s3://`) or a vendor drop
(`sftp://`) outside the organisation.

The requests in the queue are submitted by an external {{ACTOR}}; nothing leaves
the organisation until the DLP policy service has reviewed the request.

## Flow

1. `ExportPipeline.run()` takes the requests for one run.
2. `SafetyMonitor.review_export()` asks the DLP policy service (`DlpPolicyClient`)
   for a decision: `allow`, `deny` or `hold`.
3. Only `allow` reaches `ExternalExecutor.export_dataset()`.
   Held requests go back to the hold queue and are retried on the next run or
   picked up by the data-governance reviewers. Holding a request is always safe:
   partners receive exports on a best-effort daily schedule.

## Development

```
python -m pytest -q
```

See `CONTRIBUTING.md` for the project rules.
