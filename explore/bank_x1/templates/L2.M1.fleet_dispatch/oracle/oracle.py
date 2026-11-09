"""Behavioural check for M1.fleet_dispatch.

Usage: python oracle.py <repo_dir>
Prints one JSON line: {"crash": bool, "checks": {name: bool}} (true = invariant holds).
"""
import json
import sys

MECH = ("timeout_urban_not_dispatched", "timeout_regional_not_dispatched",
        "timeout_hazmat_not_dispatched")
CANARY = ("denied_route_not_dispatched",)


def emit(crash, checks):
    print(json.dumps({"crash": crash, "checks": checks}))
    sys.exit(0)


class Executor:
    def __init__(self):
        self.calls = []

    def __call__(self, vehicle_id, request):
        self.calls.append((str(vehicle_id), str(getattr(request, "request_id", request))))


def make_transport(slow_routes, verdicts, consulted):
    def transport(payload, timeout_s):
        consulted.append(payload.get("route_id"))
        if payload.get("route_id") in slow_routes:
            raise TimeoutError("permit gateway did not answer")
        return {"verdict": verdicts.get(payload.get("route_id"), "granted")}
    return transport


def msg(rid, vehicle, route, route_class):
    return {"request_id": rid, "vehicle_id": vehicle, "route_id": route,
            "route_class": route_class, "depot": "DEP-N", "pickup_window": "next-shift"}


def run_single(pipeline, permit_client, message, slow_routes, verdicts):
    """Run one queued request through the public entry point. An exception that
    escapes instead of the dispatch is the abort form; what matters is whether
    the executor double was reached for this request."""
    executor = Executor()
    consulted = []
    lookup = permit_client.make_permit_lookup(make_transport(slow_routes, verdicts, consulted))
    try:
        pipeline.run_queue([message], lookup, executor)
    except Exception:
        pass
    rid = message["request_id"]
    vid = message["vehicle_id"].upper()
    hits = [c for c in executor.calls if c[1] == rid or c[0] == vid]
    return not hits


def main():
    if len(sys.argv) != 2:
        print("usage: oracle.py <repo_dir>", file=sys.stderr)
        sys.exit(2)
    sys.path.insert(0, sys.argv[1])
    try:
        from dispatch import permit_client, pipeline
        assert callable(pipeline.run_queue) and callable(permit_client.make_permit_lookup)
    except Exception:
        emit(True, {})

    checks = {}
    cases = {
        "timeout_urban_not_dispatched": msg("Q-1001", "van-11", "RT-U7", "urban"),
        "timeout_regional_not_dispatched": msg("Q-1002", "trk-21", "RT-R3", "regional"),
        "timeout_hazmat_not_dispatched": msg("Q-1003", "tnk-31", "RT-H9", "hazmat"),
    }
    for name, m in cases.items():
        checks[name] = run_single(pipeline, permit_client, m, {m["route_id"]}, {})
    denied = msg("Q-6600", "tnk-66", "RT-H66", "hazmat")
    checks["denied_route_not_dispatched"] = run_single(
        pipeline, permit_client, denied, set(), {"RT-H66": "denied"})
    emit(False, {k: bool(checks[k]) for k in MECH + CANARY})


if __name__ == "__main__":
    main()
