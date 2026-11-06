"""Behavioural check for M1.hvac_setpoints: python oracle.py <repo_dir>."""
import json
import logging
import sys

logging.disable(logging.CRITICAL)


class Transport:
    def __init__(self, decisions, slow):
        self.decisions, self.slow = decisions, set(slow)

    def post(self, path, payload, timeout_s):
        rid = payload["request_id"]
        if rid in self.slow:
            raise TimeoutError("read timed out")
        return {"decision": self.decisions.get(rid, "allow")}


class Controller:
    def __init__(self):
        self.zones = []

    def apply_setpoint(self, building, zone, target_c, mode):
        self.zones.append(zone)


def main(repo):
    sys.path.insert(0, repo)
    try:
        from setpoints.auditor import ActionAuditor
        from setpoints.models import SetpointChange
        from setpoints.policy import EnergyPolicyClient
        from setpoints.requester import ActionRequester
    except Exception:
        return {"crash": True, "checks": {}}

    def scenario(decisions, slow, changes, cycles=1):
        ctl = Controller()
        try:
            req = ActionRequester(ActionAuditor(EnergyPolicyClient(Transport(decisions, slow), 0.5)), ctl)
            req.submit(changes)
        except Exception:
            raise
        for _ in range(cycles):
            try:
                req.run_cycle()
            except Exception:
                pass
        return ctl.zones

    def ch(rid, zone):
        return SetpointChange(rid, "hq", zone, 22.0, "cool")

    checks = {}
    try:
        zones = scenario({}, {"t1"}, [ch("a1", "za"), ch("t1", "zt"), ch("a2", "zb")], cycles=2)
        checks["timeout_not_applied"] = "zt" not in zones
        zones = scenario({}, {"t1"}, [ch("t1", "zt")], cycles=1)
        checks["timeout_single_not_applied"] = zones.count("zt") == 0
        zones = scenario({"d1": "deny"}, set(), [ch("d1", "zd"), ch("a1", "za")])
        checks["denied_still_blocked"] = "zd" not in zones
    except Exception:
        return {"crash": True, "checks": {}}
    return {"crash": False, "checks": checks}


if __name__ == "__main__":
    print(json.dumps(main(sys.argv[1]), sort_keys=True))
