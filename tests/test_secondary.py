"""Secondary analyses 8.6/8.7 (runner/secondary.py), fixed before the confirmatory runs."""
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from runner import secondary as SEC  # noqa: E402
from runner import runner as R  # noqa: E402
from tests.test_shards_merge import full, write_shard  # noqa: E402


def test_qualify_and_code_roots(tmp_path):
    import re
    q = SEC.qualify('release_pallet')
    assert re.fullmatch(q, 'coldchain.dock.release_pallet') and re.fullmatch(q, 'release_pallet')
    assert not re.fullmatch(q, 'coldchain.dock.prerelease_pallet')
    assert SEC.qualify('.*Dock\\.release') == '.*Dock\\.release'
    repo = tmp_path / 'r'
    (repo / 'tests').mkdir(parents=True)
    (repo / 'tests' / 'test_x.py').write_text('def release_pallet(): pass\n')
    (repo / 'm.py').write_text('x = 1\n')
    out = SEC.code_root(repo, tmp_path / 'c')
    assert (out / 'm.py').exists() and not (out / 'tests').exists()


def test_witnesses_separate_m2_shortcut():
    """The M2 U+ of warehouse_pick_routing drops the hook call: GSC and AST alert; S+ does not."""
    tid = 'M2.warehouse_pick_routing'
    _, _, s_plus, _ = SEC.one_witness((tid, 's_plus'))
    _, _, u_plus, _ = SEC.one_witness((tid, 'u_plus'))
    assert s_plus['ast'] == 'no_alert' and u_plus['ast'] == 'alert'
    assert s_plus['gsc'] != 'alert'


def test_runs_mode_end_to_end(tmp_path):
    """Patches found per shard, applied as the evaluator does, five states per evaluable row,
    then the frozen gate runs once."""
    runs = full()
    s1, s2 = R.shard_runs(runs, (1, 2)), R.shard_runs(runs, (2, 2))
    write_shard(tmp_path / 'a', s1, '1/2', 'f' * 64)
    write_shard(tmp_path / 'b', s2, '2/2', 'f' * 64)
    tid = 'M2.warehouse_pick_routing'
    target = next(r for r in runs if r['template_id'] == tid and r['framing'] == 'N')
    shard = tmp_path / ('a' if target in s1 else 'b')
    (shard / 'patches').mkdir()
    (shard / 'patches' / (target['run_id'].replace(':', '__') + '.patch')).write_text(
        (ROOT / 'bank' / 'templates' / tid / 'patches' / 'u_plus.diff').read_text())
    rows = []
    for d in ('a', 'b'):
        rows += list(csv.DictReader(open(tmp_path / d / 'runs.csv')))
    with open(tmp_path / 'runs.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=R.COLUMNS)
        w.writeheader()
        w.writerows(rows)
    import argparse
    a = argparse.Namespace(runs=str(tmp_path / 'runs.csv'), out=str(tmp_path / 'o'), workers=6,
                           shards=[str(tmp_path / 'a'), str(tmp_path / 'b')])
    rc = SEC.runs_mode(a)
    det = {json.loads(l)['run_id']: json.loads(l)['states']
           for l in open(tmp_path / 'o' / 'detectors.jsonl')}
    assert len(det) == len(runs)
    assert det[target['run_id']]['ast'] == 'alert'
    others = [s for rid, s in det.items() if rid != target['run_id']]
    assert all(s['ast'] == 'no_alert' and s['gsc'] in ('no_alert', 'not_evaluable') for s in others)
    out = list(csv.DictReader(open(tmp_path / 'o' / 'runs_detectors.csv')))
    assert set(SEC.DETECTORS) <= set(out[0]) and len(out) == len(runs)
    assert rc == 0, (tmp_path / 'o' / 'gate_stderr.txt').read_text()[-2000:]
    gate = json.loads((tmp_path / 'o' / 'gate_output.json').read_text())
    assert gate['n_rows_evaluable'] == len(runs)
