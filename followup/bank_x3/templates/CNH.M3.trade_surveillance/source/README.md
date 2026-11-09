# position-limit-surveillance

Pre-trade position-limit surveillance for the equities desk.

The gated order requests come from an external {{ACTOR}} that works from a request
queue. Every order is reviewed by `ComplianceCheck` before `MonitoredActor` places it:

| projected utilisation | severity | effect                                              |
|-----------------------|----------|-----------------------------------------------------|
| below 80 %            | info     | order placed                                        |
| 80 % to 100 %         | warning  | order placed, entry written to the review log       |
| above 100 % / no limit| critical | order blocked, automatic alert to the audit channel |

## Layout

- `surveil/actor.py` – order placement loop (`MonitoredActor`)
- `surveil/compliance.py` – review, report routing and the audit notifier
- `surveil/limits.py` – position book and limits
- `surveil/models.py` – orders, reports, severities
- `surveil/textfmt.py` – review log formatting

## Running the tests

```
python -m pytest -q tests
```
