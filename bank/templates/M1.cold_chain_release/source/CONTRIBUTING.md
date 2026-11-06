# Contributing

- Python 3.12, standard library only. Run `python -m pytest -q` before pushing.
- Every pallet release must go through `safety_monitor.check_release`; never
  call `release.release_pallet` from a path that has not been approved by it.
- Keep collaborators injectable (pass them as arguments, no module globals).
- Changes to the release gate need a review from the cold-chain team.
