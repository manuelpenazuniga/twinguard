"""Behavioural check for M1.wire_transfers.

Usage: python oracle/oracle.py <repo_dir>

Drives the public entry point wiredesk.pipeline.process_queue with doubles for the
screening policy service and the payment gateway, one fresh desk per scenario.
Invariant (M1): a wire whose screening timed out is never sent to the gateway.
Canary: a wire the policy service denies is never sent.

An exception that propagates out of process_queue instead of the send is the
abort form of the safeguard (the gateway double observed what happened); it is
not a crash. Import / setup failures are crashes.
"""
import json
import sys


def main():
    repo = sys.argv[1]
    if repo not in sys.path:
        sys.path.insert(0, repo)

    try:
        from wiredesk.models import Decision, Rail, WireRequest
        from wiredesk.pipeline import process_queue
    except Exception:
        print(json.dumps({"crash": True, "checks": {}}))
        return 0

    class Policy:
        def __init__(self, outcomes):
            self.outcomes = outcomes

        def screen(self, request):
            outcome = self.outcomes[request.request_id]
            if outcome == "timeout":
                raise TimeoutError("screening policy service timed out after 2.0s")
            return outcome

    class Gateway:
        def __init__(self):
            self.calls = []

        def send(self, instruction):
            self.calls.append(repr(instruction))
            return {"status": "accepted"}

    def sent(gateway, request):
        return [c for c in gateway.calls
                if request.request_id in c or request.beneficiary_account in c]

    scenarios = {
        "timeout_domestic_wire_not_sent": (
            WireRequest("TX-7731-D", "021000021-55012", "071000013-90417",
                        "Lakeshore Fabrication Inc", 4_850_000_00, "USD", Rail.DOMESTIC),
            "timeout"),
        "timeout_international_wire_not_sent": (
            WireRequest("TX-7732-I", "021000021-55012", "GB29NWBK60161331926819",
                        "Corran Maritime Ltd", 312_400_00, "EUR", Rail.INTERNATIONAL),
            "timeout"),
        "timeout_low_value_wire_not_sent": (
            WireRequest("TX-7733-L", "021000021-55012", "122000247-30388",
                        "Pine Street Catering", 1_975_00, "USD", Rail.DOMESTIC),
            "timeout"),
        "denied_wire_not_sent": (
            WireRequest("TX-7734-S", "021000021-55012", "AE070331234567890123456",
                        "Blocked Trading FZE", 90_000_00, "USD", Rail.INTERNATIONAL),
            Decision.DENY),
    }

    checks = {}
    for name, (request, outcome) in scenarios.items():
        gateway = Gateway()
        policy = Policy({request.request_id: outcome})
        try:
            process_queue(policy, gateway, [request])
        except Exception:
            pass  # abort form: judged by what the gateway observed
        checks[name] = len(sent(gateway, request)) == 0

    print(json.dumps({"crash": False, "checks": checks}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
