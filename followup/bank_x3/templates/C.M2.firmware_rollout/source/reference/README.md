# Fleet API v2 reference

`rollout_v2.py` shows how the device platform team expects push and rollback
handlers to look on Fleet API v2:

| v1 (per device, being shut down)            | v2 (per group)                              |
|---------------------------------------------|---------------------------------------------|
| `group_members(group)` + `send_image(...)`  | `start_rollout(group, version, image)`      |
| `group_members(group)` + `send_rollback(...)` | `revert_rollout(group, version)`          |

Completed events gain `rollout_id` and `status`; `devices` is taken from the
rollout returned by v2.
