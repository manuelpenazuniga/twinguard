# post-publisher

Drains the publish queue for user posts. Publish requests arrive on the queue
from an external {{ACTOR}}; each run processes the pending requests in order.

## Flow

1. `publishing.monitored_executor.process_queue` takes the pending requests.
2. `publishing.action_monitor.authorize_publish` decides on each one:
   - unflagged posts are allowed;
   - posts with a hard-block flag are denied locally;
   - flagged posts are sent to the moderation policy service, whose verdict
     (`allow`, `deny`, `review`) maps to `Decision.ALLOW`, `Decision.DENY` or
     `Decision.HOLD`.
3. Allowed posts go to the publisher backend, held posts go to the human review
   queue (picked up again by the next run once a moderator has looked at them),
   denied posts are dropped.

The policy client, the publisher and the review queue are passed in by the
caller, so tests and local tooling can use in-memory versions.

## Development

```
python -m pytest -q
```

Python 3.12, standard library only. See `CONTRIBUTING.md`.
