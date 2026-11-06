# Contributing

- Python 3.12, standard library only. Run `python -m pytest -q` before sending a change.
- Dependencies (policy transport, uploaders, queues) are passed in through
  constructors; do not instantiate network clients inside the pipeline.
- The DLP policy service is the only authority on whether a dataset may leave the
  organisation. Code in this repository must never export a dataset that the
  service has not explicitly allowed.
- Keep changes small and focused; one ticket per pull request.
