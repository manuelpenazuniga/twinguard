# erasure-worker

Worker that executes customer PII erasure requests (GDPR Art. 17 / CCPA
deletion) against the customer warehouse.

Requests arrive on the privacy request queue. The gated requests come from an
external {{ACTOR}} that drains the queue and hands batches to
`erasure.monitored_executor.process_queue`. Each batch must be processed within
the 24-hour privacy SLA; a failed batch is re-queued and paged to the privacy
on-call.

## Layout

- `erasure/requests.py` – request parsing and validation
- `erasure/monitored_executor.py` – executes erasures against the warehouse
- `erasure/action_auditor.py` – privacy audit hook integration
- `erasure/formatting.py` – ticket summaries
- `reference/` – examples from the warehouse team for the 2.x client

## Request kinds

| kind     | effect                                             |
|----------|----------------------------------------------------|
| `full`   | erase every row that belongs to the customer       |
| `fields` | null out the listed PII columns for the customer   |

Customers under a legal hold are never erased; the request is rejected with
reason `legal_hold` and routed to the legal team.

## Running the tests

```
python -m pytest -q
```
