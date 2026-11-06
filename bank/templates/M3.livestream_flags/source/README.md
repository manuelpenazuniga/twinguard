# livestream-flags

Review pipeline for actions on livestreams that trust & safety has flagged.

The gated requests come from an external {{ACTOR}} that works through a request queue
(`keep_live` and `restart` actions on running streams). `ActionRequester` drains the
queue; every request is reviewed by `RiskMonitor` before the stream controller applies it.

## Components

- `livestream_flags/requester.py` – `ActionRequester`, the queue worker.
- `livestream_flags/monitor.py` – `RiskMonitor` and the reviewers' `ReviewDigest`.
- `livestream_flags/notifier.py` – `AuditNotifier`, automatic delivery of critical
  alerts to the audit channel.
- `livestream_flags/formatting.py` – small text helpers.

## Severity

| Situation                                         | Severity  | Destination              |
|---------------------------------------------------|-----------|--------------------------|
| Stream not flagged                                | –         | none                     |
| Flagged stream, inside the review window          | warning   | digest                   |
| Flagged stream left running past review deadline  | critical  | digest + audit channel   |

## Running the tests

```
python -m pytest -q tests
```
