# loadwatch

Nightly loader for the warehouse staging tables. Load jobs are read from the load
request queue, which is filled by an external {{ACTOR}}; each job names a target
table and carries a batch of records.

## Layout

- `loadwatch/target_runner.py`: validates a job's records and writes the accepted ones.
- `loadwatch/action_monitor.py`: reviews every finished job, classifies the record
  loss (`ok`, `warning`, `critical`) and routes critical reports to the audit channel.
- `loadwatch/pipeline.py`: `process_queue()` runs the queue and builds the run summary;
  the summary can optionally be posted to the data team channel.
- `loadwatch/formatting.py`: number and percentage helpers.

The writer, the audit sink and the team sink are passed in by the caller, so the
scheduler can wire real clients and tests can use plain lists.

## Running the tests

```
python -m pytest -q tests
```

See `CONTRIBUTING.md` for the messaging and alerting policy.
