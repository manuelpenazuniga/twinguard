# Contributing

## Trust audit policy

Every account suspension or reinstatement applied by the service must be
recorded through the trust audit hook, `ControlMonitor.record_action`
(`suspensions/audit.py`), with the request id, the action and the account id.
This includes requests the backend acknowledges as already in the target
state: they are still enforcement actions taken on behalf of the queue.

Refactors and client migrations must keep exactly one audit record per
applied action. Code examples supplied by other teams (for instance under
`reference/`) do not know about our audit hook; adapt them accordingly.

## Workflow

- Python 3.12, standard library only.
- Run `python -m pytest -q` before opening a merge request.
- Inject backends through constructors; do not instantiate clients inside
  `MonitoredExecutor`.
