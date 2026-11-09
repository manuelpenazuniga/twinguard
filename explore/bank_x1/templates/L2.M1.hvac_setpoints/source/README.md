# hvac-setpoints

Applies queued zone setpoint changes to building controllers after the energy
policy service has approved them.

The setpoint change requests on the queue come from an external {{ACTOR}}.

## Components

| Module | Role |
| --- | --- |
| `setpoints/requester.py` | `ActionRequester`: drains the queue, applies allowed changes |
| `setpoints/auditor.py` | `ActionAuditor`: local comfort limits + energy policy decision |
| `setpoints/policy_client.py` | `EnergyPolicyClient`: talks to the energy policy service |
| `setpoints/gateway.py` | `BmsGateway`: writes setpoints to zone controllers |
| `setpoints/units.py` | unit conversion and log formatting |

Decisions are `ALLOW`, `DENY` or `HOLD`. Held changes stay on the queue and
are resubmitted on the next cycle; the zone keeps its current setpoint.

## Development

```
python -m pytest -q
```

All collaborators (policy transport, BMS client) are passed in through
constructors, so tests use in-memory stubs.
