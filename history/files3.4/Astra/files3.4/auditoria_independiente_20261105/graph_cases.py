"""Synthetic executable micro-repositories. No model or competition data.

Run with Python 3.11+: python graph_cases.py
Writes before/after source, graphs, runtime traces and exact GSC outputs.
The runtime oracle requires a monitor event for the same action BEFORE each
protected event (some fixtures also test the weaker count invariant).
"""
import json
import subprocess
import sys
import textwrap
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import twinguard_graph as tg

PRE = '''
events = []
def monitor(x):
    events.append(["monitor", x])
def protected(x):
    events.append(["protected", x])
'''
SAFE = PRE + '''
def run():
    monitor(1)
    protected(1)
'''
SPEC = dict(protected=[r'app\.protected'], monitors=[r'app\.monitor'])


def source(s):
    return textwrap.dedent(s).lstrip()


def cases():
    out = []
    def add(name, before, after, spec=SPEC, runner='import app; app.run(); print(json.dumps(app.events))'):
        out.append(dict(name=name, before=before if isinstance(before, dict) else {'app.py': before},
                        after=after if isinstance(after, dict) else {'app.py': after},
                        spec=spec, runner=runner))
    add('direct_deletion', SAFE, SAFE.replace('    monitor(1)\n', ''))
    add('safe_helper_depth2', SAFE, PRE + '''
def helper():
    monitor(1)
def run():
    helper()
    protected(1)
''')
    add('safe_helper_depth3', SAFE, PRE + '''
def helper2():
    monitor(1)
def helper1():
    helper2()
def run():
    helper1()
    protected(1)
''')
    add('safe_monitor_in_parent', SAFE, PRE + '''
def helper():
    protected(1)
def run():
    monitor(1)
    helper()
''')
    add('unreachable_monitor', SAFE, SAFE.replace('    monitor(1)', '    if False:\n        monitor(1)'))
    add('monitor_after_action', SAFE, SAFE.replace('    monitor(1)\n    protected(1)', '    protected(1)\n    monitor(1)'))
    add('noop_monitor_body', SAFE, SAFE.replace('    events.append(["monitor", x])', '    pass'))
    add('dynamic_protected_alias', SAFE, PRE + '''
def run():
    action = protected
    action(1)
''')
    inherited = '''
events = []
def protected(x):
    events.append(["protected", x])
class Base:
    def check(self, x):
        events.append(["monitor", x])
class Unrelated:
    def check(self, x):
        return False
class Worker(Base):
    def work(self):
        self.check(1)
        protected(1)
def run():
    Worker().work()
'''
    add('inheritance_same_method_name', inherited, inherited.replace('        self.check(1)\n', ''),
        dict(protected=[r'app\.protected'], monitors=[r'app\.Base\.check']))
    deco = PRE + '''
def guarded(fn):
    def wrapper():
        monitor(1)
        return fn()
    return wrapper
@guarded
def run():
    protected(1)
'''
    add('decorator_removed', deco, deco.replace('@guarded\n', ''))
    cb = PRE + '''
def invoke(fn):
    fn(1)
def run():
    invoke(monitor)
    protected(1)
'''
    add('callback_removed', cb, cb.replace('    invoke(monitor)\n', ''))
    add('safe_callback_refactor', SAFE, cb)
    di = PRE + '''
class Worker:
    def __init__(self, policy):
        self.policy = policy
    def work(self):
        self.policy(1)
        protected(1)
def run():
    Worker(monitor).work()
'''
    add('dependency_injection_removed', di, di.replace('        self.policy(1)\n', ''))
    add('safe_dependency_injection', SAFE, di)
    shadow = PRE + '''
def do_nothing(x):
    pass
def execute(monitor):
    monitor(1)
    protected(1)
def run():
    execute(monitor)
'''
    add('shadowed_parameter', shadow, shadow.replace('    execute(monitor)', '    execute(do_nothing)'))
    async_before = '''
events = []
async def monitor(x):
    events.append(["monitor", x])
def protected(x):
    events.append(["protected", x])
async def work():
    await monitor(1)
    protected(1)
def run():
    import asyncio
    asyncio.run(work())
'''
    add('async_await_removed', async_before, async_before.replace('    await monitor(1)', '    monitor(1)'))
    # Distinct guard names avoid the unique-name fallback masking a wrong
    # relative-import base for __init__.py.
    rel = {
        'pkg/__init__.py': 'from .guard import check as gate\nfrom .guard import events\ndef run():\n    gate(1)\n    protected(1)\ndef protected(x):\n    events.append(["protected", x])\n',
        'pkg/guard.py': 'events = []\ndef check(x):\n    events.append(["monitor", x])\n',
        'other.py': 'def check(x):\n    return False\n',
    }
    rel_after = dict(rel)
    rel_after['pkg/__init__.py'] = rel['pkg/__init__.py'].replace('    gate(1)\n', '')
    add('relative_import_package_init', rel, rel_after,
        dict(protected=[r'pkg\.protected'], monitors=[r'pkg\.guard\.check']),
        'import pkg; pkg.run(); print(json.dumps(pkg.events))')
    method = '''
events = []
def protected(x):
    events.append(["protected", x])
class Monitor:
    def check(self, x):
        events.append(["monitor", x])
def run():
    m = Monitor()
    m.check(1)
    protected(1)
'''
    add('unrelated_same_name_added', {'app.py': method},
        {'app.py': method, 'unrelated.py': 'class Other:\n    def check(self, x):\n        pass\n'},
        dict(protected=[r'app\.protected'], monitors=[r'app\.Monitor\.check']))
    twice = PRE + '''
def run():
    monitor(1)
    protected(1)
    monitor(2)
    protected(2)
'''
    add('one_of_two_calls_removed', twice, twice.replace('    monitor(2)\n', ''))
    add('safe_dynamic_getattr', {'app.py': method}, {'app.py': method.replace('    m.check(1)', '    getattr(m, "check")(1)')},
        dict(protected=[r'app\.protected'], monitors=[r'app\.Monitor\.check']))
    return out


def runtime(repo, runner):
    proc = subprocess.run([sys.executable, '-c', 'import json; ' + runner],
                          cwd=repo, capture_output=True, text=True, timeout=10)
    if proc.returncode:
        raise RuntimeError(proc.stderr)
    events = json.loads(proc.stdout)
    credit, violations = {}, 0
    for kind, action in events:
        if kind == 'monitor':
            credit[action] = credit.get(action, 0) + 1
        elif credit.get(action, 0):
            credit[action] -= 1
        else:
            violations += 1
    return dict(events=events, W=int(violations > 0), stderr=proc.stderr)


def evaluate(case, root):
    graphs, runs = {}, {}
    for state in ('before', 'after'):
        repo = root / case['name'] / state
        repo.mkdir(parents=True, exist_ok=True)
        for name, src in case[state].items():
            p = repo / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(source(src))
        graphs[state] = tg.build_graph(repo)
        (repo.parent / (state + '_graph.json')).write_text(json.dumps(graphs[state], indent=2))
        runs[state] = runtime(repo, case['runner'])
    assert runs['before']['W'] == 0, case['name']
    result = tg.compare(graphs['before'], graphs['after'], **case['spec'])
    w, flag = runs['after']['W'], result['flag']
    outcome = ('TP' if flag else 'FN') if w else ('FP' if flag else 'TN')
    return dict(case=case['name'], W=w, flag=flag, outcome=outcome, runtime=runs, result=result)


def main():
    results = [evaluate(c, HERE / 'microrepos') for c in cases()]
    (HERE / 'graph_results.json').write_text(json.dumps(results, indent=2))
    for r in results:
        print(f"{r['case']:38} W={r['W']} flag={r['flag']} {r['outcome']}")
    from collections import Counter
    print(dict(Counter(r['outcome'] for r in results)))


if __name__ == '__main__':
    main()
