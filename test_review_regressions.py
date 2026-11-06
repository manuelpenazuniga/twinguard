"""Desired-behavior regression tests against the UNMODIFIED submitted code.

Failing tests are intentional evidence, not fixes. The runtime microrepo
matrix is separate: static-analysis limitations are not all coding bugs.
"""
import ast
import sys
from pathlib import Path
import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import twinguard_graph as tg
import twinguard_analysis as ta
from test_twinguard import make_df


def repo(tmp_path, files):
    for name, src in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(src)
    return tg.build_graph(tmp_path)


def test_B01_semicolon_mutant_preserves_other_statement(tmp_path):
    src = 'def validate(x):\n    pass\ndef send(x):\n    validate(x); deliver(x)\n'
    repo(tmp_path, {'app.py': src})
    mutant = tg.guard_call_mutants(tmp_path)[0]['mutated_source']
    assert 'deliver(x)' in mutant, mutant


def test_B02_one_line_function_mutant_stays_valid(tmp_path):
    src = 'def validate(x):\n    pass\ndef run(x): validate(x)\n'
    repo(tmp_path, {'app.py': src})
    mutant = tg.guard_call_mutants(tmp_path)[0]['mutated_source']
    names = {n.name for n in ast.walk(ast.parse(mutant)) if isinstance(n, ast.FunctionDef)}
    assert 'run' in names, mutant


def test_B03_inline_if_mutant_stays_valid(tmp_path):
    src = 'def validate(x):\n    pass\ndef run(x):\n    if x: validate(x)\n    else: return 0\n'
    repo(tmp_path, {'app.py': src})
    mutant = tg.guard_call_mutants(tmp_path)[0]['mutated_source']
    ast.parse(mutant)


def test_B04_relative_import_inside_init(tmp_path):
    g = repo(tmp_path, {
        'pkg/__init__.py': 'from .guard import check as gate\ndef run():\n    gate()\n',
        'pkg/guard.py': 'def check():\n    pass\n',
        'other.py': 'def check():\n    pass\n'})
    edges = {(e['source'], e['target']) for e in g['edges']}
    assert ('pkg.run', 'pkg.guard.check') in edges, sorted(edges)


def test_B05_shadowed_parameter_not_resolved_as_global(tmp_path):
    g = repo(tmp_path, {'app.py': 'def monitor():\n    pass\ndef run(monitor):\n    monitor()\n'})
    edges = {(e['source'], e['target']) for e in g['edges']}
    assert ('app.run', 'app.monitor') not in edges, sorted(edges)


def test_B06_missing_entire_arm_is_counted():
    d = make_df()
    mask = (d.template_id == 'M1-000') & (d.framing == 'A')
    for col in ['W', 'F', 'M', 'crash']:
        d[col] = d[col].astype(float)
    d.loc[mask, ['status', 'W', 'F', 'M', 'crash']] = ['infra_failed', np.nan, np.nan, np.nan, np.nan]
    r = ta.paraphrase_gaps(d)
    assert r['n_template_framing_cells_with_missing_paraphrase'] == 1, r
    assert r['cells'] == ['M1-000/A']


def test_B07_cluster_validates_evaluable_families():
    d = make_df()
    w = ta.template_table(d, 'W')
    # Sufficient templates per mechanism, but only ONE evaluable sector.
    w['family'] = 'only_evaluable_sector'
    with pytest.raises(ta.DesignError, match='famil'):
        ta.contrast(w, 'dAN', .05, cluster='family')


def test_B08_syntax_error_is_not_silently_clean(tmp_path):
    # A rejected parse should raise or expose explicit diagnostic status.
    try:
        g = repo(tmp_path, {'broken.py': 'def broken(:\n    pass\n'})
    except (SyntaxError, ValueError):
        return
    assert g.get('parse_errors'), g


def test_B09_generic_guard_count_decrease(tmp_path):
    src = 'def validate(x):\n    pass\ndef run():\n    validate(1)\n    validate(2)\n'
    before = repo(tmp_path, {'app.py': src})
    after = repo(tmp_path, {'app.py': src.replace('    validate(2)\n', '')})
    # Optional contract extension: pair-set deletion is not call deletion.
    # Kept separate from defects B01-B08 in the report.
    assert tg.guard_edge_deletions(before, after)['flag']
