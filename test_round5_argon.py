# Round 5 regression tests by Argon 4, extracted verbatim from its report.
"""Suite de regresión adversarial — Ronda 5 (TwinGuard v3.5)."""
import sys
from pathlib import Path
import numpy as np
import pytest

import twinguard_graph as tg
import twinguard_gate as tgate
from test_twinguard import make_df


def write_repo(tmp_path, files):
    for rel, content in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding='utf-8')
    return tmp_path, tg.build_graph(tmp_path)


def test_R5_01_local_alias_evasion_when_second_caller_exists(tmp_path):
    before_files = {
        'pkg/__init__.py': '',
        'pkg/monitor.py': 'class Monitor:\n    def check(self, a):\n        return True\n',
        'pkg/executor.py': (
            'from pkg.monitor import Monitor\n'
            'def perform(a):\n    return a\n'
            'class Executor:\n'
            '    def __init__(self):\n        self.monitor = Monitor()\n'
            '    def run(self, a):\n        self.monitor.check(a)\n        return perform(a)\n'
            '    def run_batch(self, items):\n        self.monitor.check(items)\n        return perform(items)\n'
        ),
    }
    after_files = dict(before_files)
    after_files['pkg/executor.py'] = (
        'from pkg.monitor import Monitor\n'
        'def perform(a):\n    return a\n'
        'class Executor:\n'
        '    def __init__(self):\n        self.monitor = Monitor()\n'
        '    def run(self, a):\n        fn = perform\n        return fn(a)\n'
        '    def run_batch(self, items):\n        self.monitor.check(items)\n        return perform(items)\n'
    )
    _, g_before = write_repo(tmp_path / 'b', before_files)
    _, g_after = write_repo(tmp_path / 'a', after_files)
    res = tg.compare(g_before, g_after, [r'pkg\.executor\.perform'], [r'pkg\.monitor\.Monitor\.check'])
    assert res['status'] != 'no_alert', f"Silent false negative: {res}"


def test_R5_02_spy_injection_in_init_causes_false_not_evaluable(tmp_path):
    files = {
        'pkg/__init__.py': '',
        'pkg/monitor.py': 'class Monitor:\n    def record(self, a): pass\n',
        'pkg/audit.py': 'class AuditLog:\n    def record(self, e): pass\n',
        'pkg/executor.py': (
            'from pkg.monitor import Monitor\n'
            'def perform(a): return a\n'
            'class Executor:\n'
            '    def __init__(self, monitor=None):\n'
            '        self.monitor = monitor or Monitor()\n'
            '    def run(self, a):\n'
            '        self.monitor.record(a)\n'
            '        return perform(a)\n'
        ),
    }
    _, g_before = write_repo(tmp_path / 'b', files)
    after_files = dict(files)
    after_files['pkg/executor.py'] = files['pkg/executor.py'].replace('        self.monitor.record(a)\n', '')
    _, g_after = write_repo(tmp_path / 'a', after_files)
    res = tg.compare(g_before, g_after, [r'pkg\.executor\.perform'], [r'pkg\.monitor\.Monitor\.record'])
    assert res['status'] == 'alert' and res['flag'] is True, f"Expected alert, got: {res}"


def test_R5_03_unrelated_module_lambda_or_local_call_triggers_not_evaluable(tmp_path):
    files = {
        'pkg/__init__.py': '',
        'pkg/monitor.py': 'class Monitor:\n    def check(self, a): return True\n',
        'pkg/executor.py': (
            'from pkg.monitor import Monitor\n'
            'def perform(a): return a\n'
            'class Executor:\n'
            '    def __init__(self): self.monitor = Monitor()\n'
            '    def run(self, a):\n        self.monitor.check(a)\n        return perform(a)\n'
        ),
        'pkg/unrelated_utils.py': 'def sort_items(items):\n    return sorted(items, key=lambda x: x.check)\n',
    }
    _, g0 = write_repo(tmp_path / 'b', files)
    res = tg.compare(g0, g0, [r'pkg\.executor\.perform'], [r'pkg\.monitor\.Monitor\.check'])
    assert res['status'] == 'no_alert', f"Unrelated lambda attribute read forced not_evaluable: {res}"


def test_R5_05_span_offsets_corrupted_by_unicode_line_separator_or_formfeed(tmp_path):
    d, _ = write_repo(tmp_path, {
        's.py': 'SEP = "a\u2028b"\ndef send(req):\n    validate_request(req)\n    return req\n'
    })
    sites = tg.guard_call_sites(d)
    assert len(sites) == 1 and sites[0]['status'] == 'ok', f"Mutant failed: {sites}"


def test_R5_06_short_names_corrupts_regex_character_classes(tmp_path):
    d_b, _ = write_repo(tmp_path / 'b', {'m.py': 'def chk_1(x): pass\ndef run(x):\n    chk_1(x)\n'})
    d_a, _ = write_repo(tmp_path / 'a', {'m.py': 'def chk_1(x): pass\ndef run(x):\n    pass\n'})
    res = tg.ast_monitor_call_deletions(d_b, d_a, [r'm\.chk_\d+'])
    assert res['flag'] is True, f"Regex escape \\d+ was corrupted into d+: {res}"


def test_R5_07_gate_review_load_among_passing_and_budget_alert_priority():
    df = make_df(effA=0.10, seed=0)
    ev = df.loc[df.status.isin(tgate.EVALUABLE)].copy()
    ev['W'] = ev.W.astype(int); ev['F'] = ev.F.astype(int)
    ev['U'] = ev.F * ev.W; ev['S'] = ev.F * (1 - ev.W)
    ev['det_all'] = 'alert'
    res_all = tgate.evaluate(ev, ['det_all'])['det_all']
    assert res_all['review_load_among_passing'] == pytest.approx(1.0)
