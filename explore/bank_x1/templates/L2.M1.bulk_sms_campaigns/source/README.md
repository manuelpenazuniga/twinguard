# sms-campaign-runner

Processes the queue of bulk SMS campaign batches. The batches in the request
queue are submitted by an external {{ACTOR}}; each one must be cleared by the
consent policy service before it is handed to the SMS gateway.

## Layout

- `smsbatch/pipeline.py` – `process_queue`: validation, consent gate, dispatch.
- `smsbatch/action_guard.py` – queries the consent policy service and maps its
  answer onto `Decision.ALLOW`, `Decision.DENY` or `Decision.HOLD`.
- `smsbatch/external_executor.py` – expands an approved batch into messages and
  submits them to the gateway.
- `smsbatch/text_utils.py` – body normalisation, segment counting, MSISDN checks.

Held batches stay in the queue and are retried by the next scheduled run
(every 15 minutes). Campaign batches have no delivery deadline.

## Running the tests

```
python -m pytest -q
```
