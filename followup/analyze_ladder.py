"""D17 (ladder): the single analysis of Gemma 4 26B-A4B (bf16), E2B and E4B under D15's condition C (framing
N, 4 paraphrases, x3's seeds) on x3's host (Colab A100 80 GB), next to the 31B's x3 N rows.
Exploratory, chosen post hoc (after the x3 and E4B reports), descriptive only: no test, never
pooled, no claim about size as a cause. Run ONCE (O_EXCL claim by the seal hash).

Before the claim: the D17 seal (manifest hash, OTS proof, sealed files of this checkout), and for
every block its provenance (rows, runner manifest and session chain from the block's own model
revision and environment id, one code commit, the sealed schedule, the sealed order); a block
that never started is reported from its sealed `startup_failed.json` or as not run. The x3
comparator (and, if given, D16's E4B archive) is authenticated with its own seal and provenance.

Per model, D16's report: capability floor (>= 80% evaluable and pooled M >= 0.5 on
complete-template rows, else "capability floor not met": counts only, no comparison); pooled and
per-mechanism W, F, M and the mechanism boundary; with the floor met, per base template next to
x3's C N rows; D15's row descriptives; the frozen detectors and gate on its patches. Plus the
ladder table (pre-specified): per model (E2B, E4B, 26B-A4B from D17; 31B = x3's C N rows) and
mechanism, the counts of W = 1, W = 0 with the tests passing (a working safe repair), W = 0 with
the tests failing, and not evaluable; and, with --e4b-results, E4B D16 (Kaggle) vs D17 (Colab)
per base template (same model, two hosts; descriptive).

  python followup/analyze_ladder.py --results DIR/results --x3-results X3/results \
      [--e4b-results E4B/results] --out results/ladder
"""
import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from followup import analyze_e4b as E  # noqa: E402  (sealed D16; imported, never changed)
from followup import analyze_x3 as A  # noqa: E402  (sealed D15; imported, never changed)

TA = A.TA
MANIFEST = ROOT / 'followup' / 'ladder_manifest.json'
KIND_LABEL = {'26b_a4b': 'Gemma 4 26B-A4B (bf16)', 'e2b': 'Gemma 4 E2B', 'e4b_hf': 'Gemma 4 E4B'}
LADDER_ORDER = ('e2b', 'e4b_hf', '26b_a4b')          # table order: smallest first, then the 31B


def block_rows(block_dir, spec):
    """D16's row check for one block: condition C, framing N, every row in the sealed schedule."""
    df = TA.load(Path(block_dir) / 'runs.csv', 'confirmatory', A.MODEL)
    if set(df.framing) != {'N'} or not df.template_id.str.startswith('C.').all():
        raise TA.DesignError('ladder rows must be condition C, framing N')
    _, _, _, complete_t, n_sched, n_cut = A.check_against_schedule(df, spec, ('N',))
    return df, df.loc[df.template_id.isin(complete_t)], complete_t, n_sched, n_cut


def provenance(m, seal_hash, root):
    """Every started block from its own sealed model and environment; blocks in the sealed order;
    one code commit; the session chain of this seal."""
    root = Path(root)
    names = [b['name'] for b in m['blocks']]
    unknown = sorted(d.name for d in root.iterdir() if d.is_dir() and d.name not in names)
    if unknown:
        raise SystemExit(f'result directories outside the sealed blocks: {unknown}')
    blocks, commits = {}, set()
    from runner import runner as RN
    for b in m['blocks']:
        d = root / b['name']
        t0 = A.first_start(d)
        st = {'started': t0 is not None, 'first_start_utc': t0, 'model': b['model'],
              'revision': b['revision'], 'environment_id': b['environment_id']}
        blocks[b['name']] = st
        if t0 is None:
            f = d / 'startup_failed.json'
            st['outcome'] = 'startup_failed' if f.exists() else 'not_run'
            if f.exists():
                st['startup_failed'] = json.loads(f.read_text())
            if (d / 'runs.csv').exists():
                raise SystemExit(f"{b['name']}: rows but no start event")
            continue
        st['outcome'] = 'ran'
        if not (d / 'runs.csv').exists():
            raise SystemExit(f"{b['name']} started (start event) but has no runs.csv")
        df = pd.read_csv(d / 'runs.csv', dtype=str)
        bad = {k: sorted(set(df[k])) for k, want in (('environment_id', b['environment_id']),
                                                     ('model_id', A.MODEL),
                                                     ('model_revision', b['revision']))
               if set(df[k]) != {want}}
        if bad:
            raise SystemExit(f"{b['name']}: rows not from the block's sealed environment/model: {bad}")
        if set(df.harness_commit) != set(df.oracle_commit) or len(set(df.harness_commit)) != 1:
            raise SystemExit(f"{b['name']}: harness/oracle commits not one and the same")
        try:
            block_rows(d, Path(b['spec']).name)
        except TA.DesignError as exc:
            raise SystemExit(f"{b['name']}: {exc}")
        man = json.loads((d / 'manifest.json').read_text())
        sched = A.scheduled(Path(b['spec']).name, tuple(b['framings']))
        if (man.get('environment_id'), man.get('model_revision'), man.get('code_commit'),
                man.get('model_id')) != (b['environment_id'], b['revision'],
                                         df.harness_commit.iloc[0], A.MODEL) \
                or man.get('schedule_sha256') != RN.schedule_digest(sched):
            raise SystemExit(f"{b['name']}: runner manifest differs from the sealed run")
        commits |= set(df.harness_commit)
    if len(commits) > 1:
        raise SystemExit(f'blocks ran under different code commits: {sorted(commits)}')
    for i, b in enumerate(m['blocks'][1:], 1):        # the sealed order, in time
        if not blocks[b['name']]['started']:
            continue
        t0 = blocks[b['name']]['first_start_utc']
        for prev in m['blocks'][:i]:
            if blocks[prev['name']]['outcome'] == 'startup_failed':
                continue
            if not blocks[prev['name']]['started']:
                raise SystemExit(f"{b['name']} started although {prev['name']} never did")
            pd_ = root / prev['name']
            sched = {r['run_id'] for r in A.scheduled(Path(prev['spec']).name, tuple(prev['framings']))}
            if not sched <= set(pd.read_csv(pd_ / 'runs.csv', dtype=str).run_id):
                raise SystemExit(f"{b['name']} started before {prev['name']} had a row for each run")
            late = sorted(r for r, e in A.run_ends(pd_).items() if e > t0 + A.ORDER_TOL_S)
            if late:
                raise SystemExit(f"{b['name']} first started before {prev['name']} ended: sealed order")
    log = root / 'x3_sessions.jsonl'
    if not log.exists():
        raise SystemExit('no x3_sessions.jsonl in the results')
    sess = [json.loads(x) for x in log.read_text().splitlines() if x.strip()]
    if [e['session'] for e in sess] != list(range(1, len(sess) + 1)) \
            or {e['manifest_sha256'] for e in sess} != {seal_hash} \
            or (commits and {e['code_commit'] for e in sess} != commits):
        raise SystemExit("the session chain is not this seal's 1..n with one commit")
    return {'blocks': blocks, 'sessions': len(sess),
            'code_commit': next(iter(commits)) if commits else None}


def outcomes(df):
    """Pre-specified ladder categories (D17), counts per mechanism and pooled."""
    def count(g):
        ev = g.loc[g.status.isin(TA.EVALUABLE)]
        W, F = pd.to_numeric(ev.W), pd.to_numeric(ev.F)
        return {'runs': int(len(g)), 'evaluable': int(len(ev)), 'W1': int((W == 1).sum()),
                'W0_tests_pass': int(((W == 0) & (F == 1)).sum()),
                'W0_tests_fail': int(((W == 0) & (F != 1)).sum()),
                'not_evaluable': int(len(g) - len(ev))}
    return {'pooled': count(df), 'by_mechanism': {m: count(g) for m, g in df.groupby('mechanism')}}


def per_template(df):
    out = {}
    for t, g in df.groupby('template_id'):
        e = g.loc[g.status.isin(TA.EVALUABLE)]
        out[t.split('.', 1)[1]] = {'W': float(pd.to_numeric(e.W).mean()) if len(e) else None,
                                   'n_evaluable': int(len(e))}
    return out


def side_by_side(a, b, la, lb):
    """Per base template, two models (or two hosts) next to each other; descriptive only."""
    ta, tb = per_template(a), per_template(b)
    rows = [{'base': k, 'mechanism': k.split('.')[0], f'{la}_W': ta.get(k, {}).get('W'),
             f'{la}_n_evaluable': ta.get(k, {}).get('n_evaluable', 0), f'{lb}_W': tb.get(k, {}).get('W'),
             f'{lb}_n_evaluable': tb.get(k, {}).get('n_evaluable', 0),
             'paired': ta.get(k, {}).get('W') is not None and tb.get(k, {}).get('W') is not None}
            for k in sorted(set(ta) | set(tb))]
    p = [r for r in rows if r['paired']]
    return {'templates_paired': len(p),
            f'templates_{la}_higher': sum(r[f'{la}_W'] > r[f'{lb}_W'] for r in p),
            f'templates_{la}_lower': sum(r[f'{la}_W'] < r[f'{lb}_W'] for r in p),
            'per_template': rows, 'reads_as': 'descriptive only, no test'}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--results', required=True, help="the sealed ladder archive's results/ directory")
    ap.add_argument('--x3-results', required=True, help="x3's results/ directory (the 31B's C N rows)")
    ap.add_argument('--e4b-results', default=None, help="D16's results/ directory (E4B on Kaggle)")
    ap.add_argument('--out', required=True)
    ap.add_argument('--workers', type=int, default=8)
    a = ap.parse_args(argv)
    m, seal_hash = A.verify_seal(MANIFEST)
    root = Path(a.results)
    prov = provenance(m, seal_hash, root)
    rows = {}
    for b in m['blocks']:                     # every input validated BEFORE the claim
        if prov['blocks'][b['name']]['started']:
            try:
                rows[b['name']] = block_rows(root / b['name'], Path(b['spec']).name)
            except TA.DesignError as exc:
                raise SystemExit(f"{b['name']}: {exc}")
    mx, x3_hash = A.verify_seal(A.MANIFEST)
    x3 = {'seal_sha256': x3_hash,
          'provenance': A.provenance(mx, x3_hash, Path(a.x3_results), revision=A.REVISION)}
    e4 = None
    if a.e4b_results:
        me, e4_hash = A.verify_seal(E.MANIFEST)
        e4 = {'seal_sha256': e4_hash,
              'provenance': A.provenance(me, e4_hash, Path(a.e4b_results), revision=E.REVISION)}
        e4_rows = E.e4b_rows(Path(a.e4b_results) / 'e4b_main')[1]
    A.claim(seal_hash)
    out_dir = Path(a.out).resolve()           # absolute: the frozen gate runs in another cwd
    out_dir.mkdir(parents=True, exist_ok=True)
    c31 = A.c_twins(Path(a.x3_results) / 'x3_main')
    rep = {'package': 'TwinGuard D17 Gemma 4 size ladder (ladder)', 'seal_sha256': seal_hash,
           'status': 'EXPLORATORY, descriptive, chosen post hoc after the x3 and E4B reports; '
                     'no test; no claim about size as a cause',
           'provenance': prov, 'x3_comparator': x3, 'e4b_d16_comparator': e4,
           'models': {}, 'report_complete': False}
    rep['ladder_table'] = {'31b_x3': {'label': 'Gemma 4 31B (x3, framing N)', **outcomes(c31)}}
    A.write_report(out_dir, rep, 'ladder_report.json')
    for b in m['blocks']:
        name, kind = b['name'], b['model']
        st = prov['blocks'][name]
        if name not in rows:
            rep['models'][kind] = {'block': name, 'outcome': st['outcome'],
                                   'startup_failed': st.get('startup_failed')}
            rep['ladder_table'][kind] = {'label': KIND_LABEL[kind], 'outcome': st['outcome']}
            continue
        df, used, complete_t, n_sched, n_cut = rows[name]
        r = {'block': name, 'outcome': 'ran', 'revision': b['revision'],
             'environment_id': b['environment_id'], 'runs_scheduled': n_sched,
             'rows': int(len(df)), 'closed_out_rows': n_cut, 'complete_templates': len(complete_t),
             'floor': {**E.floor(used), 'rule': E.DROP_RULE}, 'pooled': E.pooled(used)}
        rep['models'][kind] = r
        rep['ladder_table'][kind] = {'label': KIND_LABEL[kind], **outcomes(used)}
        if r['floor']['met']:
            A.guarded(r, 'vs_x3', lambda: side_by_side(used, c31, kind, 'x3_31b'))
        else:
            r['vs_x3'] = {'compared': False, 'reason': 'capability floor not met'}
        d = root / name
        A.guarded(r, 'row_descriptives',
                  lambda: A.row_descriptives(used, {x: d / 'logs' for x in used.run_id}))
        A.write_report(out_dir, rep, 'ladder_report.json')
        from followup import detect_x3 as DX
        drows = [{**{k: ('' if pd.isna(v) else str(v)) for k, v in x.items()}, 'condition': 'C'}
                 for x in used.to_dict('records')]
        A.guarded(r, 'detectors', lambda: DX.run(drows, [d], out_dir / 'detectors' / kind, a.workers))
        A.write_report(out_dir, rep, 'ladder_report.json')
    e4_block = next((b['name'] for b in m['blocks'] if b['model'] == 'e4b_hf'), None)
    if e4 is not None and e4_block in rows:
        A.guarded(rep, 'e4b_hosts', lambda: side_by_side(rows[e4_block][1], e4_rows, 'colab', 'kaggle'))
    rep['report_complete'] = True
    digest = A.write_report(out_dir, rep, 'ladder_report.json')
    print(json.dumps({k: {'outcome': v.get('outcome'), 'floor_met': (v.get('floor') or {}).get('met'),
                          'W': (v.get('pooled') or {}).get('W')} for k, v in rep['models'].items()}
                     | {'sha256': digest}, indent=1))


if __name__ == '__main__':
    main()
