"""Agent-side file access and endpoint handling (Astra pre-pilot review 2026-11-07).

With run_as set, every read/write on the agent's behalf and the graph's source dump run in
a helper process (as the agent uid on Kaggle). Here the setpriv prefix is replaced by an
empty prefix so the helper path itself is exercised on any machine."""
import json
import os

import pytest

from harness import contract as C
from harness.loop import EndpointError, run_episode
from harness.tools import ToolBox
from harness.workspace import Workspace


@pytest.fixture
def ws(tmp_path, monkeypatch):
    root = tmp_path / 'repo'
    (root / 'pkg').mkdir(parents=True)
    (root / 'pkg' / 'a.py').write_text('def f():\n    return g()\n\ndef g():\n    return 1\n')
    secret = tmp_path / 'secret.py'
    secret.write_text('def leaked_symbol():\n    pass\n')
    os.symlink(secret, root / 'pkg' / 'link.py')
    w = Workspace(root, tmp_path / 'tmp', run_as='agent-uid')
    monkeypatch.setattr(Workspace, 'prefix', lambda self: [])
    monkeypatch.setattr(Workspace, 'kill_user_processes', lambda self: None)
    w.init_baseline()
    return w


def test_helper_read_write_kind(ws):
    assert ws.kind(ws.root / 'pkg' / 'a.py') == 'file'
    assert ws.kind(ws.root / 'pkg') == 'dir'
    assert ws.kind(ws.root / 'nope.py') == 'none'
    ws.write_text(ws.root / 'new' / 'deep' / 'b.py', 'x = 1\n')
    assert ws.read_text(ws.root / 'new' / 'deep' / 'b.py') == 'x = 1\n'


def test_tools_go_through_the_helper(ws):
    box = ToolBox(ws, C.Budget(tool_calls=10, time_minutes=5))
    box.start_session()
    r = json.loads(box.dispatch('read_file', json.dumps({'filepath': 'pkg/a.py'})))
    assert r['status'] == 'ok' and 'def f' in r['content']
    r = json.loads(box.dispatch('write_file', json.dumps({'filepath': 'pkg/c.py',
                                                          'content': 'def h():\n    pass\n'})))
    assert r['status'] == 'ok'
    r = json.loads(box.dispatch('edit_file', json.dumps({'filepath': 'pkg/c.py',
                                                         'old_string': 'pass',
                                                         'new_string': 'return 2'})))
    assert r['status'] == 'ok'
    assert (ws.root / 'pkg' / 'c.py').read_text() == 'def h():\n    return 2\n'


def test_graph_sources_skip_symlinks(ws):
    src = ws.py_sources()
    assert set(src) == {'pkg/a.py'}
    box = ToolBox(ws, C.Budget(tool_calls=10, time_minutes=5))
    box.start_session()
    r = json.loads(box.dispatch('get_code_neighbors', json.dumps({'node': 'f'})))
    assert 'leaked_symbol' not in json.dumps(r)
    assert box.graph.builds == 1


class Rejecting:
    model = 'fake'

    def __init__(self, status):
        self.status = status

    def chat(self, body, timeout=None):
        raise EndpointError('unprocessable', self.status, False)


def test_unprocessable_request_is_not_infrastructure(ws, tmp_path):
    s = run_episode({'repo': 'r', 'problem_statement': 'fix'}, ws, Rejecting(422),
                    C.Budget(tool_calls=10, time_minutes=5), tmp_path / 'log.jsonl',
                    {'temperature': 1.0, 'top_p': 0.95, 'top_k': 64})
    assert s['termination'] == 'bad_request'
    s = run_episode({'repo': 'r', 'problem_statement': 'fix'}, ws, Rejecting(403),
                    C.Budget(tool_calls=10, time_minutes=5), tmp_path / 'log2.jsonl',
                    {'temperature': 1.0, 'top_p': 0.95, 'top_k': 64})
    assert s['termination'] == 'config_error'


def test_model_calls_are_bounded_by_the_session_time(ws, tmp_path):
    seen = []

    class Slow:
        model = 'fake'

        def chat(self, body, timeout=None):
            seen.append(timeout)
            raise EndpointError('timed out', None, True)
    t = [0.0]

    def clock():
        t[0] += 50.0
        return t[0]
    s = run_episode({'repo': 'r', 'problem_statement': 'fix'}, ws, Slow(),
                    C.Budget(tool_calls=10, time_minutes=5), tmp_path / 'log.jsonl',
                    {'temperature': 1.0, 'top_p': 0.95, 'top_k': 64}, clock=clock,
                    sleep=lambda x: None)
    assert s['termination'] == 'time_budget'
    assert all(x is not None and x <= 300 for x in seen)
