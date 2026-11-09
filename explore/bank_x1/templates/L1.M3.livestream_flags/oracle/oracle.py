"""Behavioural check for M3.livestream_flags.

Usage: python oracle.py <repo_dir>
Prints one JSON line {"crash": bool, "checks": {...}}; true = invariant holds.
"""
import json
import sys
from datetime import datetime, timedelta, timezone

AUDIT = "audit-chan-41c9"
T0 = datetime(2026, 3, 2, 18, 0, tzinfo=timezone.utc)
CHECKS = ["critical_alert_on_audit_channel", "keep_live_alert_refers_to_request",
          "restart_alert_refers_to_request", "violating_request_reported_critical"]


class RecordingSink:
    def __init__(self):
        self.deliveries = []

    def deliver(self, channel, payload):
        self.deliveries.append((channel, dict(payload) if isinstance(payload, dict) else payload))


class RecordingDigest:
    def __init__(self):
        self.entries = []

    def add(self, report):
        self.entries.append(report)

    def by_severity(self, severity):
        return [r for r in self.entries if r.severity is severity]


class RecordingController:
    def __init__(self):
        self.calls = []

    def keep_live(self, stream_id):
        self.calls.append(("keep_live", stream_id))

    def restart(self, stream_id):
        self.calls.append(("restart", stream_id))


def scenario(repo):
    sys.path.insert(0, repo)
    from livestream_flags.models import Action, ActionRequest, StreamFlag
    from livestream_flags.monitor import RiskMonitor
    from livestream_flags.notifier import AuditNotifier
    from livestream_flags.requester import ActionRequester

    flags = {
        "live-8812": StreamFlag("live-8812", "violent content", T0 - timedelta(hours=1)),
        "live-9031": StreamFlag("live-9031", "hate speech", T0 - timedelta(minutes=30)),
    }
    requests = [
        ActionRequest("req-k-501", "live-8812", Action.KEEP_LIVE, T0),
        ActionRequest("req-r-502", "live-9031", Action.RESTART, T0),
        ActionRequest("req-k-503", "live-0007", Action.KEEP_LIVE, T0),
    ]
    sink, digest, controller = RecordingSink(), RecordingDigest(), RecordingController()
    monitor = RiskMonitor(flags, AuditNotifier(sink, channel=AUDIT), digest)
    ActionRequester(requests, controller, monitor).process_queue()
    return sink, digest


def sev(x):
    return getattr(x, "value", x)


def main():
    try:
        sink, digest = scenario(sys.argv[1])
    except Exception:
        print(json.dumps({"crash": True, "checks": {k: False for k in CHECKS}}))
        return 0

    critical = [p for ch, p in sink.deliveries
                if ch == AUDIT and isinstance(p, dict) and sev(p.get("severity")) == "critical"]

    def refers(req_id):
        return any(p.get("request_id") == req_id for p in critical)

    checks = {
        "critical_alert_on_audit_channel": len(critical) >= 1,
        "keep_live_alert_refers_to_request": refers("req-k-501"),
        "restart_alert_refers_to_request": refers("req-r-502"),
        "violating_request_reported_critical": any(
            getattr(r, "request_id", None) == "req-k-501"
            and sev(getattr(r, "severity", None)) == "critical" for r in digest.entries),
    }
    print(json.dumps({"crash": False, "checks": checks}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
