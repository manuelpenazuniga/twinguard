# Contributing

- A pallet may only be released after the cold-chain policy service has returned
  `RELEASE` for that request.
- A pallet with a `HOLD` decision stays in refrigerated staging and is picked up
  again on the next release cycle.
- Dependencies (policy service transport, dock controller) are passed in as
  arguments; keep it that way so the pipeline can be exercised with fakes.
- Standard library only. Run `python -m pytest -q tests` before opening a merge request.
