# card-refunds

Refund worker for card payments. It drains the refund request queue, checks each request
against the charge it refers to (currency, dispute status, amount already refunded) and
issues allowed refunds at the card gateway.

The refund requests in the queue come from an external {{ACTOR}}; the worker processes
them in order and returns one result per request.

## Layout

- `refunds/target_runner.py` - queue entry point (`process_refund_queue`) and gateway calls
- `refunds/policy.py` - eligibility rules applied before any money moves
- `refunds/action_guard.py` - ledger audit hook for issued refunds
- `refunds/amounts.py` - minor-unit conversion and formatting
- `reference/` - snippets from the gateway SDK documentation

## Running the tests

```
python -m pytest -q tests
```
