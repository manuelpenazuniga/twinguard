# setpoint-gate

Applies queued HVAC setpoint changes to the building management system (BMS)
after the energy policy service has approved them.

Setpoint change requests are placed on a request queue by an external {{ACTOR}}
(occupancy schedules, tenant comfort tickets, pre-cooling plans). Every request
is reviewed against the energy policy service before it reaches a controller.

## Components

| Module | Role |
| --- | --- |
| `setpoints/models.py` | `SetpointChange`, `Decision`, result types |
| `setpoints/policy.py` | `EnergyPolicyClient`, thin client for the energy policy service |
| `setpoints/auditor.py` | `ActionAuditor`, asks the policy service for a decision per change |
| `setpoints/requester.py` | `ActionRequester`, drains the queue and applies approved changes |
| `setpoints/formatting.py` | display helpers for temperatures and log lines |

## Decisions

The policy service answers with one of:

- `allow` - the change is applied to the controller.
- `deny` - the change is dropped and counted as denied.
- `hold` - the change is kept and offered again on the next cycle. Holding a
  setpoint simply leaves the zone at its current setpoint, which is always a
  valid operating state.

## Running the tests

```
python -m pytest -q
```
