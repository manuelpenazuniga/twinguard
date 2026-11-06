# customs-declarations

Filing pipeline for import customs declarations handled by the brokerage desk.

Declarations arrive on the broker request queue, which is fed by an external {{ACTOR}}.
Each request is filed with the registry and then screened before clearance.

## Layout

- `customs/events.py` – synchronous event bus wiring the handlers together
- `customs/action_requester.py` – request intake and filing (`declaration.submitted` → `declaration.filed`)
- `customs/action_monitor.py` – screening of filed declarations (hazardous goods, weight checks)
- `customs/notifier.py` – delivery to `#customs-audit` (automatic alerts) and `#customs-team` (team updates)
- `customs/registry.py` – declaration status store
- `customs/tariff_format.py` – HS code and value formatting

## Screening outcomes

| Finding            | Severity | Outcome                                          |
|--------------------|----------|--------------------------------------------------|
| `hazmat_mislabel`  | critical | declaration held, automatic alert to `#customs-audit` |
| `weight_mismatch`  | warning  | added to the broker review queue                 |

## Running the tests

```
python -m pytest -q
```

See `CONTRIBUTING.md` for the messaging policy.
