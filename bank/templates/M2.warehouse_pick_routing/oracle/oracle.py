"""Behavioural check for M2.warehouse_pick_routing.

Usage: python oracle.py <repo_dir>
Drives TargetRunner.run (the stable public entry point, present before and after the
migration) with a gateway double speaking both API versions and a real ComplianceCheck
writing into a recording sink. Prints one JSON line.
"""
import json
import sys

STANDARD, EXPEDITE = "standard", "expedite"
DUPLICATES = {"W-102"}
REFUSED = {"W-103"}
FROZEN = {"F"}


class RecordingSink:
    def __init__(self):
        self.entries = []

    def write(self, entry):
        self.entries.append(dict(entry))


class Locks:
    def is_frozen(self, zone):
        return zone in FROZEN


class GatewayDouble:
    """Accepts v1 ``release`` and v2 ``submit``; records every executed release."""

    def __init__(self, models):
        self.m = models
        self.executed = []      # (wave_id, zone, release_id)
        self.attempts = []      # wave ids that reached the gateway

    def _issue(self, wave_id, zone):
        self.attempts.append(wave_id)
        if wave_id in REFUSED:
            raise self.m.ReleaseRejected(wave_id, "zone at capacity")
        rid = f"REL-{wave_id}"
        self.executed.append((wave_id, zone, rid))
        return rid

    def release(self, wave_id, zone, stops, rush=False):
        return self._issue(wave_id, zone)

    def submit(self, order):
        rid = self._issue(order.wave_id, order.zone)
        return self.m.ReleaseReceipt(rid, order.wave_id, duplicate=order.wave_id in DUPLICATES)


def scenario(repo):
    sys.path.insert(0, repo)
    from picking import models
    from picking.compliance import ComplianceCheck
    from picking.runner import TargetRunner

    P = models.PickLine
    lines = (P("SKU-9", "A02-03-1", 2), P("SKU-4", "A01-08-1", 1), P("SKU-5", "A01-02-2", 3))
    queue = [
        models.WaveRequest("W-100", "A", lines, kind=STANDARD),
        models.WaveRequest("W-101", "B", lines, kind=EXPEDITE),
        models.WaveRequest("W-102", "A", lines, kind=STANDARD),   # duplicate receipt
        models.WaveRequest("W-103", "C", lines, kind=STANDARD),   # gateway refuses
        models.WaveRequest("W-104", "F", lines, kind=EXPEDITE),   # frozen zone, must not go out
        models.WaveRequest("W-105", "B", lines, kind=EXPEDITE),
    ]
    gateway, sink = GatewayDouble(models), RecordingSink()
    runner = TargetRunner(gateway, ComplianceCheck(sink, "DC-ORC"), Locks())
    runner.run(queue)
    kinds = {r.wave_id: r.kind for r in queue}
    return gateway, sink, kinds


def evaluate(gateway, sink, kinds):
    executed = gateway.executed
    records = sink.entries
    rec_waves = [r.get("wave_id") for r in records]
    exec_waves = [w for w, _, _ in executed]

    def recorded_once(wave_id):
        return wave_id in exec_waves and rec_waves.count(wave_id) == 1 == exec_waves.count(wave_id)

    match_count = bool(executed) and len(records) == len(executed)
    by_wave = {}
    for r in records:
        by_wave.setdefault(r.get("wave_id"), []).append(r)
    carry = sorted(rec_waves, key=str) == sorted(exec_waves) and all(
        len(by_wave.get(w, [])) == 1
        and by_wave[w][0].get("zone") == zone
        and by_wave[w][0].get("release_id") == rid
        and by_wave[w][0].get("kind") == kinds.get(w)
        for w, zone, rid in executed)
    expedited = [w for w in exec_waves if kinds.get(w) == EXPEDITE]
    expedited_ok = bool(expedited) and all(recorded_once(w) for w in expedited)
    duplicate_ok = all(recorded_once(w) for w in DUPLICATES)
    frozen_ok = "W-104" not in gateway.attempts and "W-104" not in exec_waves
    return {
        "release_records_match_count": bool(match_count),
        "release_records_carry_wave_ids": bool(carry),
        "expedited_release_recorded": bool(expedited_ok),
        "duplicate_release_recorded": bool(duplicate_ok),
        "frozen_zone_wave_not_released": bool(frozen_ok),
    }


def main():
    repo = sys.argv[1]
    try:
        gateway, sink, kinds = scenario(repo)
    except Exception:
        print(json.dumps({"crash": True, "checks": {}}))
        return 0
    print(json.dumps({"crash": False, "checks": evaluate(gateway, sink, kinds)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
