# Contributing

- Python 3.12, standard library only. Run `python -m pytest -q tests` before
  opening a merge request.
- Dependencies (transport, catalog, change-control hook) are passed in; do not
  construct clients inside handlers.
- **Change control.** Every firmware push or rollback that is sent to a device
  group must be recorded through the change-control hook
  (`ActionMonitor.record`), exactly once, with the request id, group and
  version. This applies to every rollout that completes, whatever number of
  devices it ended up touching. Rejected requests never reach the fleet and are
  not recorded.
- Keep handlers registered through `register_push_handlers`; other services
  subscribe to the completed and rejected topics.
