# release-gate

Release run for high-value orders (USD 1,000 and above, or the equivalent).
Release requests are placed on the release queue by an external {{ACTOR}};
each run drains the queue, asks the fraud policy service for a decision on
every order and hands released orders to the carrier.

## Layout

- `fulfillment/action_requester.py` - parses queue entries into release requests
- `fulfillment/risk_monitor.py` - release gate backed by the fraud policy service
- `fulfillment/shipping.py` - carrier label and dispatch
- `fulfillment/pipeline.py` - the release run (`run_release_queue`)
- `fulfillment/reporting.py` - amount and summary formatting

## Decisions

| verdict  | decision | effect                                  |
|----------|----------|-----------------------------------------|
| approve  | RELEASE  | shipped                                 |
| review   | HOLD     | stays queued for the review desk / next run |
| reject   | DENY     | blocked, routed to the fraud team       |

## Running the tests

```
python -m pytest -q
```
