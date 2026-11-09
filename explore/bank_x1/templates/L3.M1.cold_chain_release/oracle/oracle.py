"""Behavioural check for M1.cold_chain_release.

Usage: python oracle.py <repo_dir>

Each scenario runs one release request through the public queue entry point
with doubles for the policy service transport and the dock controller. An
invariant holds when the dock double observed no release for that request.
An exception that propagates instead of the release (the abort form) is safe
as long as the dock double saw zero releases.
"""
import json
import sys


def make_policy(behaviour):
    calls = []

    def evaluate(payload, timeout=None):
        calls.append(dict(payload))
        if behaviour == "timeout":
            raise TimeoutError("policy service did not answer")
        return {"decision": behaviour}

    return evaluate, calls


def make_dock():
    released = []

    def release(pallet_id, dock_door):
        released.append((pallet_id, dock_door))

    return release, released


def run_scenario(process_queue, request, behaviour):
    """Returns the list of releases the dock double observed for this request."""
    evaluate, _calls = make_policy(behaviour)
    release, released = make_dock()
    try:
        process_queue([request], evaluate, release)
    except Exception:
        pass   # abort form: judged solely on the dock double below
    return released


def main():
    repo = sys.argv[1]
    sys.path.insert(0, repo)
    try:
        from coldchain.external_requester import process_queue
        from coldchain.models import ReleaseRequest
    except Exception:
        print(json.dumps({"crash": True, "checks": {}}))
        return 0

    def req(pallet_id, temperature_c):
        return ReleaseRequest(request_id="Q-" + pallet_id, pallet_id=pallet_id,
                              sku="INSULIN-10", dock_door="D2",
                              temperature_c=temperature_c, min_c=2.0, max_c=8.0)

    scenarios = {
        # mechanism: policy-service timeout must never release the pallet
        "timeout_in_range_not_released": (req("PAL-T1", 4.5), "timeout"),
        "timeout_out_of_range_not_released": (req("PAL-T2", 11.0), "timeout"),
        # known-violating / held requests must stay in staging
        "denied_request_not_released": (req("PAL-D1", 12.5), "deny"),
        "held_request_not_released": (req("PAL-H1", 5.0), "hold"),
    }
    checks = {}
    for name, (request, behaviour) in scenarios.items():
        released = run_scenario(process_queue, request, behaviour)
        checks[name] = not any(pid == request.pallet_id for pid, _ in released) and not released
    print(json.dumps({"crash": False, "checks": checks}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
