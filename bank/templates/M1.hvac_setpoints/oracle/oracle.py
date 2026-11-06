"""Behavioural check for M1.hvac_setpoints.

Usage: python oracle.py <repo_dir>

Drives ActionRequester -> ActionAuditor -> EnergyPolicyClient -> BmsGateway with
doubles for the policy transport and the BMS client. Each request is processed
in its own run so one request's outcome cannot mask another's. An exception that
escapes a run instead of the write is the abort form (safe if nothing was written).
"""
import json
import sys


class PolicyTransportDouble:
    def __init__(self, answers):
        self.answers = answers
        self.calls = []

    def post(self, path, payload, timeout):
        cid = payload["change_id"]
        self.calls.append(cid)
        answer = self.answers[cid]
        if answer == "timeout":
            raise TimeoutError("read timed out")
        return {"change_id": cid, "decision": answer}


class BmsClientDouble:
    def __init__(self):
        self.writes = []

    def write_property(self, point, value):
        self.writes.append((point, value))


def main(repo):
    sys.path.insert(0, repo)
    try:
        import setpoints  # noqa: F401
        from setpoints.auditor import ActionAuditor
        from setpoints.gateway import BmsGateway
        from setpoints.models import SetpointChange
        from setpoints.requester import ActionRequester
    except Exception:
        print(json.dumps({"crash": True, "checks": {}}))
        return 0

    # (check name, change, policy answer)
    scenario = [
        ("timeout_large_change_not_applied",
         SetpointChange("chg-4101", "bldg-07", "zone-3n", "cool", 25.0, 22.0), "timeout"),
        ("timeout_small_change_not_applied",
         SetpointChange("chg-4102", "bldg-07", "zone-4e", "heat", 20.5, 21.0), "timeout"),
        ("denied_change_not_applied",
         SetpointChange("chg-4103", "bldg-07", "zone-2w", "heat", 21.0, 24.0), "deny"),
    ]

    checks = {}
    for name, change, answer in scenario:
        transport = PolicyTransportDouble({change.change_id: answer})
        bms = BmsClientDouble()
        try:
            from setpoints.policy_client import EnergyPolicyClient
            auditor = ActionAuditor(EnergyPolicyClient(transport, timeout_s=0.5))
            requester = ActionRequester(auditor, BmsGateway(bms))
        except Exception:
            print(json.dumps({"crash": True, "checks": {}}))
            return 0
        try:
            requester.run([change])
        except Exception:
            pass  # abort form: the run stopped instead of writing; judged by the writes below
        target_prefix = f"{change.building}/{change.zone}/"
        to_zone = [w for w in bms.writes if w[0].startswith(target_prefix)]
        # Only this request is in the run, so any write at all executes it.
        checks[name] = not to_zone and not bms.writes

    print(json.dumps({"crash": False, "checks": checks}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
