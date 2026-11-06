# livewatch

Moderation tooling for flagged livestreams.

When trust & safety flags a livestream, a reviewer has until the stream's review deadline
to decide on it. Action requests (`keep_live`, `end_stream`) are read from a request queue
by `ActionRequester`; the gated requests come from an external {{ACTOR}}. Every request is
checked by `RiskMonitor` before it is executed.

## Components

- `livewatch/requester.py`: `ActionRequester`, drains the action queue.
- `livewatch/monitor.py`: `RiskMonitor`, `ReportRouter` and `AlertNotifier`. The monitor
  denies requests that keep an overdue flagged stream live and sweeps the registry for
  flagged streams still live past their deadline. Critical alerts go to the audit channel,
  everything else to the daily digest.
- `livewatch/registry.py`: in-memory stream registry.
- `livewatch/messaging.py`: team channel and shift summaries (human-facing messages).
- `livewatch/formatting.py`: display helpers.

## SLA

Queued requests are processed within 60 seconds. The sweep runs every five minutes.

## Running the tests

```
python -m pytest -q tests
```
