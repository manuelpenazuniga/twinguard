# Contributing

## Clinical audit

Every release of a lab result to the patient portal must be recorded through the
clinical audit hook (`RiskMonitor.record_release`) as soon as the portal confirms it,
with the release id the portal returned. This applies to final and amended results
alike. Changes to release paths that skip the audit record will not be merged.

## Results under clinician review

Results whose test code is configured in `ReleaseHoldPolicy` must never reach the portal
before review; they are announced on `release.held` instead.

## Style

- Standard library only, Python 3.12.
- Dependencies (portal client, audit hook, hold policy) are passed in, never imported
  as globals, so they can be replaced in tests.
- Run `python -m pytest -q` before opening a merge request.
