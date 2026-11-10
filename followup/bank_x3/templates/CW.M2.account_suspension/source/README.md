# account-enforcement

Applies account suspensions and reinstatements from the moderation request
queue. The gated requests come from an external {{ACTOR}} that works through
the queue under the same 15-minute SLA as every other enforcement source.

## Layout

- `suspensions/executor.py` – `MonitoredExecutor`, drains the queue
  (`run`, `process`).
- `suspensions/policy.py` – pre-flight checks (protected accounts, reasons).
- `suspensions/accounts.py` – accounts backend clients (legacy and v2 gateway).
- `suspensions/audit.py` – trust audit hook (`ControlMonitor`).
- `suspensions/notices.py` – account-holder notice text.
- `reference/` – migration example from the accounts platform team.

See `CONTRIBUTING.md` for the audit policy.

## Tests

    python -m pytest -q
