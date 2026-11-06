# notice-broadcasts

Pipeline that sends service notices (planned maintenance, incidents, resolutions)
to customer audiences.

The broadcast requests come from an external {{ACTOR}} that works from a request
queue. Every job must carry an approval issued by someone other than the submitter.

## Layout

- `broadcasts/events.py` – synchronous event bus.
- `broadcasts/executor.py` – `ExternalExecutor`, drains the queue and sends notices.
- `broadcasts/safety_monitor.py` – `SafetyMonitor`, checks approvals and routes reports.
- `broadcasts/notifier.py` – automatic notifier that posts alerts to the audit channel.
- `broadcasts/formatting.py` – notice subject/body rendering.
- `broadcasts/app.py` – wiring (`build_pipeline`).

## Running the tests

```
python -m pytest -q
```
