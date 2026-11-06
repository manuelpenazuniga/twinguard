# Contributing

- A pallet may only be released after the cold-chain policy service has returned
  `RELEASE` for that request. Do not add release paths that bypass `check_release`.
- `HOLD` is always an acceptable outcome: the pallet stays in refrigerated staging
  and is picked up again on the next release cycle.
- Dependencies (policy service transport, dock controller) are passed in as
  arguments; keep it that way so the pipeline can be exercised with fakes.
- Standard library only. Run `python -m pytest -q tests` before opening a merge request.
