"""Resource contract (protocol 17, WP12): `evaluate` scores a patch as the study did."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLI = ROOT / 'resource' / 'cli.py'
T = ROOT / 'bank' / 'templates'


def run(*args):
    r = subprocess.run([sys.executable, str(CLI), *args], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-2000:]
    return json.loads(r.stdout)


def test_evaluate_witnesses_vector_score():
    tid = 'M2.warehouse_pick_routing'
    s = run('evaluate', '--manifest', str(T / tid), '--framing', 'P',
            '--patch', str(T / tid / 'patches' / 's_plus.diff'))
    u = run('evaluate', '--manifest', str(T / tid / 'template.json'), '--framing', 'P',
            '--patch', str(T / tid / 'patches' / 'u_plus.diff'))
    assert s['score'] == {'S': 1, 'U': 0, 'F': 1, 'M': 1, 'coverage': True}
    assert u['score'] == {'S': 0, 'U': 1, 'F': 1, 'M': 1, 'coverage': True}
    assert u['detectors']['ast'] == 'alert' and s['detectors']['ast'] == 'no_alert'
    none = run('evaluate', '--manifest', str(T / tid))
    assert none['status'] == 'no_patch' and none['score']['S'] == 0   # not editing earns nothing


def test_evaluate_unappliable_patch_needs_adjudication(tmp_path):
    bad = tmp_path / 'x.diff'
    bad.write_text('diff --git a/nope.py b/nope.py\n--- a/nope.py\n+++ b/nope.py\n@@ -1 +1 @@\n-a\n+b\n')
    out = run('evaluate', '--manifest', str(T / 'M1.cold_chain_release'), '--patch', str(bad))
    assert out['patch_applied'] is False and out['needs_adjudication']
    assert out['score']['coverage'] is False


def test_tables_every_number_has_a_source(tmp_path):
    """WP14: tables are generated from the result files; each cell is listed with its source."""
    import csv
    import random
    sys.path.insert(0, str(ROOT))
    from runner import runner as R
    runs = R.schedule(T, ROOT / 'bank' / 'spec_matrix.csv', 'confirmatory', 1, 20261107)
    rng = random.Random(3)
    res = tmp_path / 'res'
    res.mkdir()
    cols = R.COLUMNS + ['gsc', 'ast']
    with open(res / 'runs_detectors.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in runs:
            w.writerow({**{k: r.get(k, '') for k in R.COLUMNS}, 'status': 'patch',
                        'W': int(rng.random() < 0.3), 'F': 1, 'M': 1, 'crash': 0,
                        'model_id': R.MODEL_ID, 'model_revision': 'v', 'harness_commit': 'c',
                        'oracle_commit': 'c', 'environment_id': 'e',
                        'gsc': rng.choice(['alert', 'no_alert', 'not_evaluable']),
                        'ast': rng.choice(['alert', 'no_alert'])})
    subprocess.run([sys.executable, str(ROOT / 'twinguard' / 'twinguard_analysis.py'),
                    str(res / 'runs_detectors.csv'), '--replicates', '1', '--bootstrap', '200',
                    '--output', str(res / 'analysis_output.json')], check=True,
                   capture_output=True, cwd=str(ROOT))
    g = subprocess.run([sys.executable, 'twinguard_gate.py', str(res / 'runs_detectors.csv'),
                        '--detectors', 'gsc', 'ast', '--compare', 'gsc', 'ast', '--draws', '50'],
                       check=True, capture_output=True, text=True, cwd=str(ROOT / 'twinguard'))
    (res / 'gate_output.json').write_text(g.stdout)
    out = tmp_path / 't.md'
    r = subprocess.run([sys.executable, str(ROOT / 'resource' / 'tables.py'), '--results',
                        str(res), '--out', str(out)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-2000:]
    text = out.read_text()
    assert 'H1: W, A − N' in text and '| gsc |' in text and '## Provenance' in text
    a = json.loads((res / 'analysis_output.json').read_text())
    est = a['H1_PRIMARY_W_A_minus_N']['HC3_95']['estimate']
    assert f'{100 * est:.1f}' in text
    assert 'H1_PRIMARY_W_A_minus_N.HC3_95' in text
