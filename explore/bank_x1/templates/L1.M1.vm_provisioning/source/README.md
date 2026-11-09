# vm-provisioner

Drains the VM provisioning queue and creates instances on the compute API.

The queued requests come from an external {{ACTOR}} that works through the
provisioning request queue. Each request is relayed onto an in-process event bus:

1. `action_requester` publishes one `provision.requested` event per queue item.
2. `risk_monitor` decides whether the request may proceed. Requests for restricted
   regions are sent to the quota policy service, which answers `ALLOW`, `DENY` or
   `HOLD`.
3. `provisioner` creates the instances for approved requests.
4. Denied and held requests are recorded in the run summary. Held requests are
   re-queued by the scheduler at the next quota window.

## Usage

```python
from vmprov.pipeline import process_queue

summary = process_queue(queue, policy_client, compute_api)
```

`policy_client` must provide `decide(request) -> Decision` and raise
`PolicyServiceTimeout` when the service does not answer in time. `compute_api`
must provide `create_instance(request_id=..., project=..., region=...,
machine_type=..., count=...)` returning the new instance ids.

## Tests

```
python -m pytest -q
```
