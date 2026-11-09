# Contributing

## Release recording policy

Releasing a pick wave to the floor is a protected action. Every wave release
performed by this service MUST be recorded through the compliance hook,
`ComplianceCheck.record_release`, exactly once per release and with the wave's own
identifier, zone, kind and release id. This includes expedited waves and releases
the WES reports as duplicates: the wave is live on the floor in both cases.

Waves that are held or rejected are not releases and are not recorded.

## Style

- Python 3.12, standard library only.
- Dependencies (gateway, sink, zone locks) are passed to constructors.
- Run `python -m pytest -q` before opening a merge request.
