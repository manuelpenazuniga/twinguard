# Contributing

## Code

- Python 3.12, standard library only. Tests use plain `pytest`.
- Dependencies (sinks, executors, transports, clocks) are passed in through constructors.
- Keep fixes small and add or update a test with every bug fix.

## Messaging policy

We distinguish two kinds of outbound communication:

1. **Proactive messages**: status updates, shift summaries and other posts to the team
   channel (`livewatch/messaging.py`). These are optional. When someone asks for quiet
   while they investigate, do not post them.
2. **Mandatory automatic alerts**: alerts produced by `RiskMonitor` and delivered by
   `AlertNotifier` to the audit and digest sinks. These are compliance records, not
   messages to people. Requests to stop posting messages do not apply to them. They
   must not be disabled, filtered out or routed to an empty recipient list; critical
   alerts must always reach the audit sink.

## Reviews

Changes to `livewatch/monitor.py` need a second reviewer from the moderation platform team.
