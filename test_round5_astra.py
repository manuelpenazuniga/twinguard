# Round 5 regression tests by GPT-6 Astra, unchanged except the import path.
"""Desired-behavior regressions: intentionally fail on supplied v3.5.
No original source edits. Synthetic inputs only.
"""
import ast
import sys
from pathlib import Path
import pandas as pd
import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import twinguard_graph as gr
import twinguard_gate as gate
from test_twinguard import make_df


def write(root, source, encoding='utf-8'):
    root.mkdir(parents=True, exist_ok=True)
    (root / 'app.py').write_bytes(source.encode(encoding))
    return root


@pytest.mark.parametrize('col,value', [('W', .9), ('W', 2), ('F', 2)])
def test_R01_gate_rejects_nonbinary(tmp_path, col, value):
    d = make_df(); d[col] = d[col].astype(float)
    d.loc[0, col] = value; d['gsc'] = 'no_alert'
    path = tmp_path/'data.csv'; d.to_csv(path, index=False)
    with pytest.raises(ValueError):
        gate.load(path, ['gsc'])


def test_R02_duplicate_run_id_rejected_before_budget(tmp_path):
    d = make_df(); d['gsc'] = 'no_alert'
    d['run_id'] = 'same_id'
    path = tmp_path/'data.csv'; d.to_csv(path, index=False)
    with pytest.raises(ValueError):
        gate.load(path, ['gsc'])


def test_R03_latin1_mutant_preserves_unrelated_literal(tmp_path):
    src = '# coding: latin-1\nlabel = "café"\ndef validate(x): pass\ndef run():\n    validate(label)\n'
    write(tmp_path, src, 'latin-1')
    m = gr.guard_call_mutants(tmp_path)[0]['mutated_source']
    assert 'label = "café"' in m, m


def test_R04_unicode_line_separator_does_not_shift_span(tmp_path):
    src = 'def validate(x): pass\nlabel = "a\u2028b"\nvalidate(1)\nvalidate(2)\n'
    write(tmp_path, src)
    site = next(x for x in gr.guard_call_sites(tmp_path) if x['line'] == 4)
    assert site['status'] == 'ok', site
    expected = 'def validate(x): pass\nlabel = "a\u2028b"\nvalidate(1)\npass\n'
    assert site['mutated_source'] == expected, site


def test_R05_missing_protected_symbol_is_not_evaluable(tmp_path):
    b = write(tmp_path/'b', 'def monitor(): pass\ndef protected(): pass\ndef run():\n    monitor()\n    protected()\n')
    a = write(tmp_path/'a', 'def monitor(): pass\ndef run():\n    return 1\n')
    r = gr.compare(gr.build_graph(b), gr.build_graph(a), [r'app\.protected'], [r'app\.monitor'])
    assert r['status'] == 'not_evaluable', r


def test_R06_missing_manifest_matches_are_not_clean(tmp_path):
    root = write(tmp_path, 'def f(): return 1\n')
    g = gr.build_graph(root)
    r = gr.compare(g, g, [r'app\.nonexistent'], [r'app\.absent'])
    assert r['status'] == 'not_evaluable', r


def test_R07_definition_time_call_not_runtime_edge(tmp_path):
    root = write(tmp_path, 'def monitor(): pass\ndef protected(): pass\ndef run(token=monitor()):\n    protected()\n')
    g = gr.build_graph(root)
    edges = {(e['source'],e['target']) for e in g['edges']}
    assert ('app.run','app.monitor') not in edges, edges


def test_R08_multiple_inheritance_honors_python_mro(tmp_path):
    src = 'class A:\n    def check(self): pass\nclass B(A): pass\nclass C(A):\n    def check(self): pass\nclass D(B,C):\n    def run(self): self.check()\n'
    g = gr.build_graph(write(tmp_path,src))
    edges = {(e['source'],e['target']) for e in g['edges']}
    # A sound fallback may leave this unresolved; it must not call A exact.
    assert ('app.D.run','app.A.check') not in edges, edges
