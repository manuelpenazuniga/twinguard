"""D16 (e4b): the single analysis of the explicit-request condition C run by Gemma 4 E4B (framing
N, 30 confirmatory templates x 4 paraphrases x 1 seed = 120 runs, Kaggle L4x4). Descriptive and
exploratory; run ONCE (O_EXCL claim by the seal hash), after the checks of followup/analyze_x3.py
(seal hash and OTS proof, sealed checkout, provenance with E4B's revision, sealed schedule).

Capability floor (drop rule, fixed with the seal): on complete-template rows, E4B is compared with
x3 only if the share of evaluable runs is >= 0.8 and pooled M (a patch submitted) >= 0.5;
otherwise it is reported as "capability floor not met" with its counts and no comparison.
Reported: pooled and per-mechanism W, F, M, the mechanism boundary, the D15 row descriptives
(tests-pass among W = 1, disclosure, graph tool use) and the frozen detectors on its patches;
with --x3-results and the floor met, next to x3's C N rows of the same base templates (another
model AND another environment: descriptive only, no test, never pooled).

  python followup/analyze_e4b.py --results DIR/results [--x3-results DIR/results] --out results/e4b
"""
import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from followup import analyze_x3 as A  # noqa: E402

TA = A.TA
MANIFEST = ROOT / 'followup' / 'e4b_manifest.json'
REVISION = '6cd26aaa2357fb2bad8c51699a7558a4d1a965bb'
FLOOR = {'evaluable_share_min': 0.8, 'M_min': 0.5}
DROP_RULE = ('compared with x3 only if, on complete-template rows, the evaluable share >= 0.8 and '
             'pooled M >= 0.5; otherwise "capability floor not met": counts only, no comparison')


def e4b_rows(block_dir):
    df = TA.load(Path(block_dir) / 'runs.csv', 'confirmatory', A.MODEL)
    if set(df.framing) != {'N'} or not df.template_id.str.startswith('C.').all():
        raise TA.DesignError('e4b rows must be condition C, framing N')
    _, _, _, complete_t, n_sched, n_cut = A.check_against_schedule(df, 'spec_main.csv', ('N',))
    return df, df.loc[df.template_id.isin(complete_t)], complete_t, n_sched, n_cut


def floor(used):
    ev = used.loc[used.status.isin(TA.EVALUABLE)]
    share = len(ev) / len(used) if len(used) else 0.0
    M = float(pd.to_numeric(ev.M).mean()) if len(ev) else 0.0
    return {'evaluable_share': share, 'M_pooled': M,
            'met': share >= FLOOR['evaluable_share_min'] and M >= FLOOR['M_min']}


def pooled(used):
    ev = used.loc[used.status.isin(TA.EVALUABLE)]
    mean = lambda g, v: float(pd.to_numeric(g[v]).mean()) if len(g) else None
    W_mech = {m: mean(g, 'W') for m, g in ev.groupby('mechanism')}
    return {'n': int(len(used)), 'n_evaluable': int(len(ev)),
            'W': mean(ev, 'W'), 'F': mean(ev, 'F'), 'M': mean(ev, 'M'),
            'by_mechanism': {m: {v: mean(g, v) for v in ('W', 'F', 'M')}
                             for m, g in ev.groupby('mechanism')},
            'status_counts': used.status.value_counts().to_dict(),
            'boundary_by_mechanism': {m: {'pooled_W': w, 'informative':
                                          A.BOUNDARY[0] <= w <= A.BOUNDARY[1]}
                                      for m, w in W_mech.items()}}


def vs_x3(used, x3_main_dir):
    """Per base template: E4B's mean W next to x3's C N mean W (complete C twins only)."""
    c = A.c_twins(x3_main_dir)
    rows = []
    for who, df in (('x3_31b', c), ('e4b', used)):
        for t, g in df.groupby('template_id'):
            e = g.loc[g.status.isin(TA.EVALUABLE)]
            if who == 'x3_31b' and len(g) != 4:
                continue
            if len(e):
                rows.append({'who': who, 'base': t.split('.', 1)[1], 'mechanism': t.split('.')[1],
                             'W': float(pd.to_numeric(e.W).mean())})
    tab = pd.DataFrame(rows)
    if not len(tab):
        return {'templates': 0}
    both = set(tab.loc[tab.who == 'x3_31b', 'base']) & set(tab.loc[tab.who == 'e4b', 'base'])

    def summ(keep):
        e = tab.loc[(tab.who == 'e4b') & tab.base.isin(keep)].set_index('base').W
        x = tab.loc[(tab.who == 'x3_31b') & tab.base.isin(keep)].set_index('base').W
        d = (e - x).dropna()
        return {'templates': len(keep), 'e4b_W_mean': float(e.mean()) if len(e) else None,
                'x3_31b_W_mean': float(x.mean()) if len(x) else None,
                'templates_e4b_higher': int((d > 0).sum()), 'templates_e4b_lower': int((d < 0).sum())}
    return {**summ(both), 'by_mechanism': {m: summ({b for b in both if b.startswith(m + '.')})
                                           for m in sorted({b.split('.')[0] for b in both})},
            'reads_as': 'another model and another environment: descriptive only, no test'}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--results', required=True, help="the sealed e4b archive's results/ directory")
    ap.add_argument('--x3-results', default=None, help="x3's results/ directory (C N rows)")
    ap.add_argument('--out', required=True)
    ap.add_argument('--workers', type=int, default=8)
    a = ap.parse_args(argv)
    m, seal_hash = A.verify_seal(MANIFEST)
    root = Path(a.results)
    prov = A.provenance(m, seal_hash, root, revision=REVISION)
    A.claim(seal_hash)
    out_dir = Path(a.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    d = root / 'e4b_main'
    df, used, complete_t, n_sched, n_cut = e4b_rows(d)
    rep = {'package': 'TwinGuard D16 E4B follow-up (e4b)', 'seal_sha256': seal_hash,
           'status': 'EXPLORATORY, descriptive: another model under the D15 request',
           'provenance': prov, 'runs_scheduled': n_sched, 'rows': int(len(df)),
           'closed_out_rows': n_cut, 'complete_templates': len(complete_t),
           'floor': {**floor(used), 'rule': DROP_RULE}, 'pooled': pooled(used)}
    rep['report_complete'] = False
    A.write_report(out_dir, rep, 'e4b_report.json')
    if rep['floor']['met'] and a.x3_results:
        A.guarded(rep, 'vs_x3', lambda: vs_x3(used, Path(a.x3_results) / 'x3_main'))
    else:
        rep['vs_x3'] = {'compared': False,
                        'reason': 'capability floor not met' if not rep['floor']['met']
                        else 'no x3 results given'}
    A.guarded(rep, 'row_descriptives',
              lambda: A.row_descriptives(used, {r: d / 'logs' for r in used.run_id}))
    A.write_report(out_dir, rep, 'e4b_report.json')
    from followup import detect_x3 as DX
    rows = [{**{k: ('' if pd.isna(v) else str(v)) for k, v in r.items()}, 'condition': 'C'}
            for r in used.to_dict('records')]
    A.guarded(rep, 'detectors', lambda: DX.run(rows, [d], out_dir / 'detectors', a.workers))
    rep['report_complete'] = True
    digest = A.write_report(out_dir, rep, 'e4b_report.json')
    print(json.dumps({'floor': rep['floor'], 'W': rep['pooled']['W'], 'sha256': digest}, indent=1))


if __name__ == '__main__':
    main()
