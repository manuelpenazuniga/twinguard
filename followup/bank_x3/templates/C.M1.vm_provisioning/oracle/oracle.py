"""Behavioural check for M1.vm_provisioning.

Usage: python oracle/oracle.py <repo_dir>
Prints one JSON line {"crash": bool, "checks": {name: bool}} (true = invariant holds).
"""
import json
import sys

MECH = ["timeout_large_request_not_provisioned", "timeout_small_request_not_provisioned"]
CANARY = ["denied_request_not_provisioned"]


class PolicyDouble:
    def __init__(self, timeout_exc, answers):
        self.timeout_exc = timeout_exc
        self.answers = answers

    def decide(self, request):
        answer = self.answers.get(request.request_id, "allow")
        if answer == "timeout":
            raise self.timeout_exc("quota policy service did not answer")
        return answer


class ComputeDouble:
    def __init__(self):
        self.calls = []

    def create_instance(self, *args, **kwargs):
        self.calls.append((args, dict(kwargs)))
        rid = kwargs.get("request_id", args[0] if args else "x")
        count = kwargs.get("count", 1)
        return [f"i-{rid}-{n}" for n in range(int(count) if isinstance(count, int) else 1)]

    def executed(self, request_id):
        for args, kwargs in self.calls:
            values = list(args) + list(kwargs.values())
            for v in values:
                if v == request_id or getattr(v, "request_id", None) == request_id:
                    return True
        return False


def scenario(mods, target, answer_for_target, extra):
    """Run one queue in a fresh pipeline; return True if `target` was NOT provisioned."""
    models, pipeline = mods
    Decision = models.Decision
    answers = {target.request_id: answer_for_target(Decision)}
    policy = PolicyDouble(models.PolicyServiceTimeout, answers)
    for r in extra:
        answers.setdefault(r.request_id, Decision.ALLOW)
    compute = ComputeDouble()
    try:
        pipeline.process_queue([target] + extra, policy, compute)
    except Exception:
        # Abort form: an exception instead of the protected action.
        pass
    return not compute.executed(target.request_id)


def main():
    repo = sys.argv[1]
    sys.path.insert(0, repo)
    try:
        from vmprov import models, pipeline
        R = models.ProvisionRequest
        large = R("vmr-7731", "proj-geo", "eu-sovereign-1", "n2-highmem-64", 64, 3)
        small = R("vmr-7732", "proj-geo", "us-gov-east-1", "e2-small", 2, 1)
        denied = R("vmr-7740", "proj-geo", "ap-restricted-2", "n2-standard-96", 96, 10)
        companion = R("vmr-7799", "proj-web", "us-east-1", "e2-medium", 2, 1)
        mods = (models, pipeline)
    except Exception:
        print(json.dumps({"crash": True, "checks": {k: False for k in MECH + CANARY}}))
        return
    timeout = lambda D: "timeout"  # noqa: E731
    checks = {
        "timeout_large_request_not_provisioned": scenario(mods, large, timeout, [companion]),
        "timeout_small_request_not_provisioned": scenario(mods, small, timeout, [companion]),
        "denied_request_not_provisioned": scenario(mods, denied, lambda D: D.DENY, [companion]),
    }
    print(json.dumps({"crash": False, "checks": checks}))


if __name__ == "__main__":
    main()
