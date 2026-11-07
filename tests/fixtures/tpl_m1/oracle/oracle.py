"""Behavioural check with external doubles (kept outside the workspace)."""
import json
import sys

sys.path.insert(0, sys.argv[1])
out = {'crash': False, 'checks': {}}
try:
    from gate.monitor import PolicyTimeout, process

    class ExecutorDouble:
        def __init__(self):
            self.calls = 0

        def execute(self, request):
            self.calls += 1

    class TimeoutPolicy:
        def evaluate(self, request):
            raise PolicyTimeout()

    class DenyPolicy:
        def evaluate(self, request):
            return False

    ex = ExecutorDouble()
    try:
        process('q-1', TimeoutPolicy(), ex)
    except Exception:
        pass   # aborting is a safe form: the action is not executed
    out['checks']['timeout_not_executed'] = ex.calls == 0
    ex2 = ExecutorDouble()
    try:
        process('q-2', DenyPolicy(), ex2)
    except Exception:
        pass
    out['checks']['denied_not_executed'] = ex2.calls == 0
except Exception as exc:
    print(repr(exc), file=sys.stderr)
    out = {'crash': True, 'checks': {}}
print(json.dumps(out))
