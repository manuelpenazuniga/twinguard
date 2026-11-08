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
