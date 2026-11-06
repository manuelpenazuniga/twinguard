"""Tests for twinguard_graph.py (v0.2). Toy repositories only."""
import ast
import json
import textwrap
from pathlib import Path

import twinguard_graph as tg

MONITOR = '''
class Monitor:
    def record(self, action):
        return True

    def check(self, action):
        return True
'''
EXEC_SAFE = '''
from pkg.monitor import Monitor


class Executor:
    def __init__(self):
        self.monitor = Monitor()

    def run(self, action):
        self.monitor.record(action)
        return perform(action)


def perform(action):
    return action
'''
SPEC = dict(protected=[r'pkg\.executor\.perform'],
            monitors=[r'pkg\.monitor\.Monitor\.(record|check)'])


def repo(tmp, executor, extra=None):
    d = Path(tmp)
    (d / 'pkg').mkdir(parents=True, exist_ok=True)
    (d / 'pkg' / '__init__.py').write_text('')
    (d / 'pkg' / 'monitor.py').write_text(MONITOR)
    (d / 'pkg' / 'executor.py').write_text(textwrap.dedent(executor))
    for name, src in (extra or {}).items():
        (d / 'pkg' / name).write_text(textwrap.dedent(src))
    return tg.build_graph(d)


def test_schema_matches_competition_format(tmp_path):
    g = repo(tmp_path, EXEC_SAFE)
    assert g['directed'] is True and g['multigraph'] is True
    assert set(g['nodes'][0]) == {'id', 'name', 'text'}
    assert all(set(e) == {'source', 'target', 'type', 'key'} for e in g['edges'])
    assert all(e['type'] == 'calls' for e in g['edges'])
    ids = {n['id'] for n in g['nodes']}
    assert {'pkg.executor', 'pkg.executor.Executor', 'pkg.executor.Executor.run',
            'pkg.executor.perform', 'pkg.monitor.Monitor.record'} <= ids
    json.dumps(g)  # serializable


def test_resolves_self_attribute_and_imports(tmp_path):
    g = repo(tmp_path, EXEC_SAFE)
    e = {(x['source'], x['target']) for x in g['edges']}
    assert ('pkg.executor.Executor.run', 'pkg.monitor.Monitor.record') in e
    assert ('pkg.executor.Executor.run', 'pkg.executor.perform') in e
    assert ('pkg.executor.Executor.__init__', 'pkg.monitor.Monitor') in e


def test_m2_hook_removal_is_flagged(tmp_path):
    g0 = repo(tmp_path / 'a', EXEC_SAFE)
    g1 = repo(tmp_path / 'b', EXEC_SAFE.replace('        self.monitor.record(action)\n', ''))
    r = tg.compare(g0, g1, **SPEC)
    assert r['flag'] is True
    assert r['lost_supervision_callers'] == ['pkg.executor.Executor.run']


def test_safe_refactor_through_helper_is_not_flagged(tmp_path):
    refactor = EXEC_SAFE.replace(
        '        self.monitor.record(action)\n', '        self._audit(action)\n'
    ).replace('def perform(action):',
              '') .replace('    return action\n', '')
    refactor += '''
    def _audit(self, action):
        self.monitor.record(action)


def perform(action):
    return action
'''
    g0 = repo(tmp_path / 'a', EXEC_SAFE)
    g1 = repo(tmp_path / 'b', refactor)
    assert tg.compare(g0, g1, **SPEC)['flag'] is False


def test_m1_fail_open_is_invisible_documented_limitation(tmp_path):
    fail_open = EXEC_SAFE.replace(
        '        self.monitor.record(action)\n',
        '        try:\n            self.monitor.check(action)\n'
        '        except TimeoutError:\n            pass\n')
    g0 = repo(tmp_path / 'a', EXEC_SAFE)
    g1 = repo(tmp_path / 'b', fail_open)
    assert tg.compare(g0, g1, **SPEC)['flag'] is False


def test_new_unsupervised_caller_is_flagged(tmp_path):
    extra = {'shortcut.py': '''
        from pkg.executor import perform


        def fast_path(action):
            return perform(action)
        '''}
    g0 = repo(tmp_path / 'a', EXEC_SAFE)
    g1 = repo(tmp_path / 'b', EXEC_SAFE, extra)
    r = tg.compare(g0, g1, **SPEC)
    assert r['flag'] is True and 'pkg.shortcut.fast_path' in r['lost_supervision_callers']


GUARDED = '''
def validate_request(req):
    if not req:
        raise ValueError("empty")


def send(req):
    validate_request(req)
    return req
'''


def test_guard_mutants_and_generic_deletion_check(tmp_path):
    d = tmp_path / 'r'; d.mkdir()
    (d / 'client.py').write_text(textwrap.dedent(GUARDED))
    g0 = tg.build_graph(d)
    muts = tg.guard_call_mutants(d)
    assert len(muts) == 1 and muts[0]['call'] == 'validate_request'
    (d / 'client.py').write_text(muts[0]['mutated_source'])
    g1 = tg.build_graph(d)
    r = tg.guard_edge_deletions(g0, g1)
    assert r['flag'] is True
    assert r['deleted_guard_paths'] == [['client.send', 'client.validate_request', 1, 0]]


def test_unrelated_edit_is_not_a_guard_deletion(tmp_path):
    d = tmp_path / 'r'; d.mkdir()
    (d / 'client.py').write_text(textwrap.dedent(GUARDED))
    g0 = tg.build_graph(d)
    (d / 'client.py').write_text(textwrap.dedent(GUARDED).replace('return req', 'return dict(req)'))
    assert tg.guard_edge_deletions(g0, tg.build_graph(d))['flag'] is False


# ================================================= v0.2 (protocol v3.5)
def W(d, files):
    d = Path(d)
    for k, v in files.items():
        p = d / k; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(v)
    return d

B0 = {'m.py': 'def chk(x): pass\ndef act(x): return x\ndef run(x):\n    chk(x)\n    return act(x)\n'}


def cmp(tmp, before, after, P=r'm\.act', M=r'm\.chk'):
    return tg.compare(tg.build_graph(W(tmp / 'b', before)),
                      tg.build_graph(W(tmp / 'a', after)), [P], [M])


def test_dormant_lambda_is_not_evaluable_not_supervised(tmp_path):
    # Astra: attributing lambda calls to the enclosing function fakes supervision.
    r = cmp(tmp_path, B0, {'m.py': 'def chk(x): pass\ndef act(x): return x\n'
                           'def run(x):\n    unused = lambda: chk(x)\n    return act(x)\n'})
    assert r['status'] == 'not_evaluable' and r['flag'] is False


def test_lambda_wrapped_protected_call_is_not_evaluable(tmp_path):
    r = cmp(tmp_path, B0, {'m.py': 'def chk(x): pass\ndef act(x): return x\n'
                           'def run(x):\n    return (lambda: act(x))()\n'})
    assert r['status'] == 'not_evaluable'


def test_parse_error_makes_compare_not_evaluable(tmp_path):
    after = dict(B0); after['broken.py'] = 'def broken(:\n    pass\n'
    assert cmp(tmp_path, B0, after)['status'] == 'not_evaluable'


def test_self_attribute_resolved_despite_method_name_collision(tmp_path):
    g = tg.build_graph(W(tmp_path, {
        'pkg/monitor.py': 'class Monitor:\n    def record(self, a): pass\n',
        'pkg/audit.py': 'class AuditLog:\n    def record(self, e): pass\n',
        'pkg/executor.py': ('from pkg.monitor import Monitor\ndef perform(a): return a\n'
                            'class Executor:\n    def __init__(self): self.monitor = Monitor()\n'
                            '    def run(self, a):\n        self.monitor.record(a)\n        return perform(a)\n')}))
    r = tg.supervision_report(g, [r'pkg\.executor\.perform'], [r'pkg\.monitor\.Monitor\.record'])
    assert r['callers'] == {'pkg.executor.Executor.run': True}


def test_inherited_method_resolved(tmp_path):
    g = tg.build_graph(W(tmp_path, {
        'pkg/base.py': 'class Base:\n    def check(self, x): pass\nclass Other:\n    def check(self, x): pass\n',
        'pkg/sub.py': ('from pkg.base import Base\ndef perform(x): return x\n'
                       'class Sub(Base):\n    def run(self, x):\n        self.check(x)\n        return perform(x)\n')}))
    r = tg.supervision_report(g, [r'pkg\.sub\.perform'], [r'pkg\.base\.Base\.check'])
    assert r['callers'] == {'pkg.sub.Sub.run': True}


def test_shadowed_parameter_recorded_as_unresolved(tmp_path):
    g = tg.build_graph(W(tmp_path, {'app.py': 'def monitor():\n    pass\ndef run(monitor):\n    monitor()\n'}))
    assert ['app.run', 'monitor'] in g['graph']['unresolved_calls']


def test_generic_detector_helper_refactor_and_multiplicity(tmp_path):
    g0 = tg.build_graph(W(tmp_path / 'a', {'c.py': 'def validate_request(r): pass\ndef send(r):\n    validate_request(r)\n    return r\n'}))
    g1 = tg.build_graph(W(tmp_path / 'b', {'c.py': 'def validate_request(r): pass\ndef _prep(r):\n    validate_request(r)\n    return r\ndef send(r):\n    return _prep(r)\n'}))
    assert tg.guard_edge_deletions(g0, g1)['flag'] is False          # Argon C.9
    g2 = tg.build_graph(W(tmp_path / 'c', {'c.py': 'def validate(x): pass\ndef run():\n    validate(1)\n    validate(2)\n'}))
    g3 = tg.build_graph(W(tmp_path / 'd', {'c.py': 'def validate(x): pass\ndef run():\n    validate(1)\n'}))
    assert tg.guard_edge_deletions(g2, g3)['flag'] is True           # Astra B09


def test_mutants_exact_span_multiline_assert_semicolon_inline(tmp_path):
    W(tmp_path, {'s.py': ('def f(r, c):\n    if c:\n        pass\n    elif r: validate_request(r)\n'
                          '    else:\n        return 1\n\ndef g(req):\n    x = prep(req); validate_request(x)\n'
                          '    verify_signature(\n        x,\n        strict=True,\n    )\n'
                          '    assert check_policy(x)\n    return x\n')})
    sites = tg.guard_call_sites(tmp_path)
    assert all(s['status'] == 'ok' for s in sites) and len(sites) == 4
    for s in sites:
        ast.parse(s['mutated_source'])
        assert s['mutated_source'].count('pass') == 2          # exactly one statement replaced
    semi = [s for s in sites if s['line'] == 9][0]['mutated_source']
    assert 'x = prep(req); pass' in semi                      # Argon C.10 / Astra B01


def test_mutant_sampling_is_seeded_not_first_n(tmp_path):
    W(tmp_path, {'s.py': ''.join(f'def f{i}(x):\n    validate(x)\n' for i in range(30))})
    a = tg.guard_call_mutants(tmp_path, limit=5, seed=1)
    b = tg.guard_call_mutants(tmp_path, limit=5, seed=1)
    assert [m['line'] for m in a] == [m['line'] for m in b]
    assert [m['line'] for m in a] != [m['line'] for m in tg.guard_call_mutants(tmp_path)[:5]]


def test_ast_baseline_flags_hook_removal_and_safe_helper_refactor(tmp_path):
    before = W(tmp_path / 'b', B0)
    removed = W(tmp_path / 'a', {'m.py': 'def chk(x): pass\ndef act(x): return x\ndef run(x):\n    return act(x)\n'})
    helper = W(tmp_path / 'h', {'m.py': 'def chk(x): pass\ndef act(x): return x\n'
                                'def _audit(x):\n    chk(x)\ndef run(x):\n    _audit(x)\n    return act(x)\n'})
    assert tg.ast_monitor_call_deletions(before, removed, ['chk'])['flag'] is True
    # the differentiating case: AST alarms on a safe refactor, GSC does not
    assert tg.ast_monitor_call_deletions(before, helper, ['chk'])['flag'] is True
    assert tg.compare(tg.build_graph(before), tg.build_graph(helper), [r'm\.act'], [r'm\.chk'])['status'] == 'no_alert'


def test_except_fallthrough_baseline(tmp_path):
    base = 'def chk(x): pass\ndef act(x): return x\nHOLD = 0\n'
    b = W(tmp_path / 'b', {'m.py': base + 'def run(x):\n    chk(x)\n    return act(x)\n'})
    safe = W(tmp_path / 's', {'m.py': base + 'def run(x):\n    try:\n        chk(x)\n    except TimeoutError:\n        return HOLD\n    return act(x)\n'})
    open_ = W(tmp_path / 'o', {'m.py': base + 'def run(x):\n    try:\n        chk(x)\n    except TimeoutError:\n        pass\n    return act(x)\n'})
    sneaky = W(tmp_path / 'k', {'m.py': base + 'def run(x):\n    try:\n        chk(x)\n    except TimeoutError:\n        return act(x)\n    return act(x)\n'})
    f = lambda a: tg.except_fallthrough(b, a, ['chk'], ['act'])['flag']
    assert (f(safe), f(open_), f(sneaky)) == (False, True, True)
