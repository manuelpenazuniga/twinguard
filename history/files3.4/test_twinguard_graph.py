"""Tests for twinguard_graph.py (GSC v0.1). Toy repositories only."""
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
    assert r['deleted_guard_edges'] == [('client.send', 'client.validate_request')]


def test_unrelated_edit_is_not_a_guard_deletion(tmp_path):
    d = tmp_path / 'r'; d.mkdir()
    (d / 'client.py').write_text(textwrap.dedent(GUARDED))
    g0 = tg.build_graph(d)
    (d / 'client.py').write_text(textwrap.dedent(GUARDED).replace('return req', 'return dict(req)'))
    assert tg.guard_edge_deletions(g0, tg.build_graph(d))['flag'] is False
