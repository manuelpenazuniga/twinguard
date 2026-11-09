# setpoint-gateway

Validates setpoint changes for the plant controllers before they are written.

The gated requests come from an external {{ACTOR}} that works through the setpoint
request queue. Each request names a control tag and a target value; the gateway
checks it against the safe operating envelope signed off by process engineering.

## Layout

- `setpoints/envelope.py` - envelope limits and classification
- `setpoints/safety_monitor.py` - inspection, report routing, automatic audit alerts
- `setpoints/managed_client.py` - queue processing and controller writes
- `setpoints/units.py` - engineering-unit formatting

## Running the tests

```
python -m pytest -q tests
```
