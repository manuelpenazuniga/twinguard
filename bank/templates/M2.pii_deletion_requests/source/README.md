# pii-erasure-worker

Worker that drains the customer-data deletion request queue and erases the
matching customer records from the record store.

The gated requests come from an external {{ACTOR}} that reads them from the
deletion request queue; each request is checked against policy (identity
verification, legal holds, erasable tables) before anything is erased.

## Layout

- `erasure/requests.py` - parsing of queue messages into `ErasureRequest`
- `erasure/policy.py` - eligibility rules (legal holds, verification, tables)
- `erasure/store_api.py` - types of the record-store client 2.0 API
- `erasure/monitored_executor.py` - drains the queue and performs erasures
- `erasure/action_auditor.py` - privacy audit hook for performed erasures
- `erasure/report_format.py` - text reports for run summaries
- `reference/` - an already migrated worker from another team, for the v2 API

## Running the tests

```
python -m pytest -q tests
```

All collaborators (record store, audit hook, legal-hold lookup) are passed in
as arguments, so tests use in-memory fakes.
