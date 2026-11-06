# Contributing

- Python 3.12, standard library only. Run `python -m pytest -q tests` before opening a merge request.
- Dependencies (policy transport, cabinet driver) are passed in through constructors; do not
  instantiate network clients inside the pipeline classes.
- Pharmacy policy: medication is loaded into a cabinet only when the formulary policy
  service has approved the order. Every change to `watch_guard.py` or `executor.py` needs a
  review from the pharmacy informatics team.
- Keep the run report complete: every order taken from the queue must appear in it.
