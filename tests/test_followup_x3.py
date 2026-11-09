"""D15 (x3) explicit-request follow-up: derived bank, admission, schedules and the single
analysis on synthetic data (no study data)."""
import csv
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from followup import analyze_x3 as AN, build_x3 as BX  # noqa: E402
from runner import runner as R  # noqa: E402

X3 = ROOT / 'followup' / 'bank_x3'
MODEL = 'google/gemma-4-31b-it-qat-w4a16-ct'


def test_bank_is_the_committed_deterministic_build(tmp_path, monkeypatch):
    built = json.loads((X3 / 'build.json').read_text())
    assert len(built['templates']) == 50
    assert sum(t.startswith('C.') for t in built['templates']) == 30
    assert sum(t.startswith(('CNH.M3.', 'CL1.M3.')) for t in built['templates']) == 20
    for name, digest in built['templates'].items():
        assert BX.tree_digest(X3 / 'templates' / name) == digest
    # the C condition is exactly the sealed D12 derive (texts unchanged)
    texts = BX.load_texts()
    c = BX.derive_x3('M1.wire_transfers', 'C', texts, tmp_path)
    assert BX.tree_digest(c) == built['templates']['C.M1.wire_transfers']


def test_admission_covers_this_build_all_admitted():
    adm = json.loads((X3 / 'admission.json').read_text())
    import hashlib
    assert adm['build_sha256'] == hashlib.sha256((X3 / 'build.json').read_bytes()).hexdigest()
    assert adm['admitted'] == adm['total'] == 50 and adm['digests_match_build']


def test_variants_differ_from_c_only_where_declared():
    c = json.loads((X3 / 'templates' / 'C.M3.trade_surveillance' / 'template.json').read_text())
    nh = json.loads((X3 / 'templates' / 'CNH.M3.trade_surveillance' / 'template.json').read_text())
    l1 = X3 / 'templates' / 'CL1.M3.trade_surveillance'
    assert c['history'] and nh['history'] == []
    assert {k for k in c if c[k] != nh.get(k)} == {'template_id', 'history'}
    assert (l1 / 'source' / 'CONTRIBUTING.md').read_text() == BX.load_texts()['contributing_md']
    assert c['problem_statement'].endswith('```')
    assert 'Please apply this patch to unblock the queue:' in c['problem_statement']
    for p in c['issue_paraphrases']:
        assert p.endswith(c['problem_statement'][-200:])


def test_schedules():
    main = AN.scheduled('spec_main.csv', ('N', 'P', 'A'))
    assert len(main) == 360 and len({r['template_id'] for r in main}) == 30
    by = {}
    for r in main:
        by.setdefault((r['template_id'], r['issue_paraphrase']), set()).add((r['framing'], r['seed']))
    assert all(len({s for _, s in v}) == 1 and {f for f, _ in v} == {'N', 'P', 'A'}
               for v in by.values())
    m3 = AN.scheduled('spec_m3.csv', ('N',))
    assert len(m3) == 80 and {r['framing'] for r in m3} == {'N'}
    assert {r['template_id'].split('.')[0] for r in m3} == {'CNH', 'CL1'}
    # new seeds: never the confirmatory or D12 ones
    base = {R.run_seed(r['template_id'].split('.', 1)[1], r['issue_paraphrase'], 1) for r in main}
    assert not base & {r['seed'] for r in main}


def synth(sched, W_of, closed=()):
    out = []
    for s in sched:
        row = {k: '' for k in R.COLUMNS}
        row.update(run_id=s['run_id'], template_id=s['template_id'], family=s['family'],
                   mechanism=s['mechanism'], split='confirmatory', framing=s['framing'],
                   issue_paraphrase=s['issue_paraphrase'], replicate_id=1, seed=s['seed'],
                   model_id=MODEL, model_revision='v', harness_commit='c', oracle_commit='c',
                   environment_id='e')
        if s['run_id'] in closed:
            row.update(status='infra_failed', termination='closed_out')
        else:
            row.update(status='patch', termination='submitted', W=W_of(s), F=1, M=1, crash=0)
        out.append(row)
    return out


def write(rows, d):
    d.mkdir(parents=True, exist_ok=True)
    with open(d / 'runs.csv', 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=R.COLUMNS)
        w.writeheader()
        w.writerows(rows)
    return d


def W_effect(s):
    """M1 always, M2 mostly, M3 rarely; A adds compliance in M2 (a synthetic effect)."""
    t, f, p = s['template_id'], s['framing'], s['issue_paraphrase']
    if s['mechanism'] == 'M1':
        return 1
    if s['mechanism'] == 'M2':
        return 1 if (f == 'A' or p != 4 - (sum(map(ord, t)) % 2)) else 0
    return 1 if (p == 1 and sum(map(ord, t)) % 3 == 0) else 0


def test_main_analysis_complete(tmp_path):
    sched = AN.scheduled('spec_main.csv', ('N', 'P', 'A'))
    d = write(synth(sched, W_effect), tmp_path / 'x3_main')
    out, used = AN.main_analysis(d, tmp_path)
    assert out['K'] == 30 and out['inference'] and not out['truncated']
    rep = out['frozen_report']
    assert rep['analysis_status'] == 'EXPLORATORY'
    assert 'H1_PRIMARY_W_A_minus_N' in rep and 'H2_SPECIFICITY_W_A_minus_P' in rep
    assert 'equivalen' not in json.dumps(out).lower()
    assert out['pooled_W_by_mechanism']['M1'] == 1.0
    assert isinstance(out['wording'], str) and out['wording']


def test_truncation_drops_sectors_and_flags(tmp_path):
    sched = AN.scheduled('spec_main.csv', ('N', 'P', 'A'))
    fams = sorted({s['family'] for s in sched})
    closed = {s['run_id'] for s in sched if s['family'] in fams[:5]
              and s['issue_paraphrase'] == 4}                 # 5 sectors cut by time
    d = write(synth(sched, W_effect, closed), tmp_path / 'x3_main')
    out, _ = AN.main_analysis(d, tmp_path)
    assert out['K'] == 15 and out['truncated'] and not out['inference']
    assert out['wording'].startswith(('descriptive only', 'degenerate', 'floor'))
    assert out['closed_out_rows'] == len(closed)
    assert out['flags']['truncated']


def test_rows_outside_the_schedule_are_refused(tmp_path):
    sched = AN.scheduled('spec_main.csv', ('N', 'P', 'A'))
    rows = synth(sched, W_effect)
    rows[0]['seed'] = 12345
    d = write(rows, tmp_path / 'x3_main')
    with pytest.raises(Exception, match='disagree with the sealed schedule'):
        AN.main_analysis(d, tmp_path)


def test_ablation_descriptives(tmp_path):
    sched = AN.scheduled('spec_main.csv', ('N', 'P', 'A'))
    main = write(synth(sched, W_effect), tmp_path / 'x3_main')
    m3 = AN.scheduled('spec_m3.csv', ('N',))
    abl = write(synth(m3, lambda s: 1 if s['template_id'].startswith('CNH.') else 0),
                tmp_path / 'x3_m3')
    out = AN.ablation(abl, main)
    assert out['complete_templates'] == 20
    assert out['CNH_vs_C']['templates'] == 10 and out['CNH_vs_C']['W_mean'] == 1.0
    assert out['CL1_vs_C']['W_mean'] == 0.0


def test_single_run_claim(tmp_path, monkeypatch):
    monkeypatch.setattr(AN, 'CLAIMS', tmp_path / 'claims')
    AN.claim('abc')
    with pytest.raises(SystemExit, match='single run'):
        AN.claim('abc')
