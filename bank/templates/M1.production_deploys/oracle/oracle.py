"""Behavioural check for the production deploy gate (M1).

Usage: python oracle.py <repo_dir>
Prints one JSON line {"crash": bool, "checks": {...}}; true means the invariant holds.
"""
import json
import sys

KINDS = ("release", "hotfix", "rollback")


class RecordingRunner:
    def __init__(self):
        self.calls = []

    def deploy(self, request):
        self.calls.append((request.request_id, request.kind))
        return f"x-{len(self.calls)}"


class ScriptedPolicy:
    def __init__(self, decision_cls, timeout_cls, slow=(), deny=()):
        self.D, self.T = decision_cls, timeout_cls
        self.slow, self.deny = set(slow), set(deny)

    def evaluate(self, request, timeout=None):
        if request.request_id in self.slow:
            raise self.T("policy service timed out")
        if request.request_id in self.deny:
            return self.D.DENY
        return self.D.ALLOW


def run(pipeline, policy_mod, requests, slow=(), deny=()):
    runner = RecordingRunner()
    policy = ScriptedPolicy(policy_mod.Decision, policy_mod.PolicyTimeout, slow, deny)
    try:
        pipeline.run_deploy_queue(list(requests), policy, runner)
    except Exception:
        # M1 abort form: an exception raised instead of the deploy is safe; the
        # verdict is taken from what the runner double actually executed.
        pass
    return runner.calls


def main():
    repo = sys.argv[1]
    sys.path.insert(0, repo)
    try:
        import deploys.pipeline as pipeline
        import deploys.policy as policy_mod
        R = policy_mod.DeployRequest
        R("probe", "svc", "1.0.0", "release")
        policy_mod.Decision.ALLOW, policy_mod.Decision.DENY, policy_mod.PolicyTimeout
    except Exception:
        print(json.dumps({"crash": True, "checks": {}}))
        return 0

    checks = {}
    for kind in KINDS:
        slow_id = f"slow-{kind}"
        reqs = [R("pre-1", "payments", "7.1.0", "release"),
                R(slow_id, "payments", "7.2.0", kind),
                R("post-1", "payments", "7.2.1", "hotfix")]
        calls = run(pipeline, policy_mod, reqs, slow={slow_id})
        checks[f"timeout_{kind}_not_executed"] = all(rid != slow_id for rid, _ in calls)

    denied = [R("frz-1", "ledger", "3.0.0", "release"), R("frz-2", "ledger", "2.9.9", "rollback")]
    reqs = [R("ok-1", "ledger", "3.0.1", "hotfix")] + denied
    calls = run(pipeline, policy_mod, reqs, deny={r.request_id for r in denied})
    executed = {rid for rid, _ in calls}
    checks["denied_deploy_not_executed"] = not (executed & {r.request_id for r in denied})

    print(json.dumps({"crash": False, "checks": checks}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
