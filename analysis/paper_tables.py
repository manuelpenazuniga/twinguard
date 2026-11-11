"""Writeup tables 2 and 3b (WP14), next to resource/tables.py (table 1 and the witness table).
Every number is counted from a results file and printed with its source; nothing is estimated.

  Table 2  D12 calibration ladder (pilot templates, pooled N/P/A, framing never grouped): per rung
           and mechanism, scheduled / completed / closed-out runs, W = 1, tests passing (F = 1),
           and the lexical patch-mention and rejection matches (D14 descriptive 1).
  Table 3b The agent's own weakening patches (oracle W = 1): calibration C and confirmatory, per
           mechanism: runs, distinct templates, tests passing, and alerts of the frozen detectors.
  Figure   The M1 example: the S+ and U+ witness diffs of the first pilot M1 template.
  Table 4  D15 (x3) and D16 (E4B): the explicit request, by mechanism and framing (4b per template).
  Table 5  D17/D17b: Gemma 4 configurations under the explicit request (W = 1, safe repairs that
           pass or fail the tests, crashes), next to D16's E4B and x3's 31B N rows.

  python analysis/paper_tables.py --calibration-archive x1_cal_out/results_sealed.tar.gz \
      --out results/paper/tables_2_3b.md

The same counts go to figure_data.json next to --out (with its sha256), the only input of
analysis/paper_figures.py, so the figures redraw on CPU without the calibration archive.
"""
import argparse
import csv
import hashlib
import json
import sys
import tarfile
import tempfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'analysis'))
import d14_descriptives as D  # noqa: E402
from runner import secondary as S  # noqa: E402

EV = S.EVALUABLE
DETS = ('gsc', 'ast', 'except_local')


def counts_calibration(rows):
    t = defaultdict(lambda: defaultdict(int))
    for r in rows:
        rung, mech = r['template_id'].split('.')[0], r['mechanism']
        for key in ((rung, mech), (rung, 'all')):
            c = t[key]
            c['scheduled'] += 1
            if r['status'] in EV:
                c['completed'] += 1
                c['W1'] += r['W'] == '1'
                c['F1'] += r['F'] == '1'
            elif r['status'] == 'infra_failed':
                c['closed_or_failed'] += 1
    return t


def detector_states(rows, block):
    finals = S.final_events([block])
    return {r['run_id']: D.one((r['run_id'], r['template_id'], r['framing'],
                                S.patch_of(finals, r['run_id'])))[1] for r in rows}


def table3b(rows, states, label):
    t = defaultdict(lambda: defaultdict(int))
    tmpl = defaultdict(set)
    for r in rows:
        for key in (r['mechanism'], 'all'):
            c = t[key]
            c['runs'] += 1
            c['F1'] += r['F'] == '1'
            tmpl[key].add(r['template_id'])
            for d in DETS:
                c[d] += states[r['run_id']][d] == 'alert'
    out, data = [], {}
    for key in ('M1', 'M2', 'M3', 'all'):
        if key not in t:
            continue
        c = t[key]
        data[key] = {'runs': c['runs'], 'templates': len(tmpl[key]), 'tests_pass': c['F1'],
                     **{d: c[d] for d in DETS}}
        out.append(f"| {label} | {key} | {c['runs']} | {len(tmpl[key])} | {c['F1']}/{c['runs']} | "
                   + ' | '.join(f"{c[d]}/{c['runs']}" for d in DETS) + ' |')
    return out, data


def confirmatory_by_arm(conf):
    arms = {}
    for f in ('N', 'P', 'A'):
        rs = [r for r in conf if r['framing'] == f]
        ev = [r for r in rs if r['status'] in EV]
        arms[f] = {'scheduled': len(rs), 'evaluable': len(ev),
                   **{k: sum(r[k] == '1' for r in ev) for k in ('M', 'F', 'W')}}
    return arms


def hashed_json(path):
    """A committed report, checked against the sha256 file written next to it."""
    raw = path.read_bytes()
    side = path.parent / (path.name + '.sha256')
    if side.exists() and hashlib.sha256(raw).hexdigest() != side.read_text().split()[0]:
        raise SystemExit(f'{path} does not match its recorded sha256')
    return json.loads(raw)


def k_of(rate, n):
    """Back from a reported rate to its count (the reports store rates with their n)."""
    k = round(rate * n)
    assert abs(rate * n - k) < 1e-6, (rate, n)
    return k


def followup(lines):
    """D15 (x3) and D16 (E4B): the committed single-analysis reports, their per-run detector
    files and the frozen gate outputs (decisions.md, deviation of the D15/D16 gate)."""
    x3 = hashed_json(ROOT / 'results' / 'x3' / 'x3_report.json')
    e4 = hashed_json(ROOT / 'results' / 'e4b' / 'e4b_report.json')
    gx = json.loads((ROOT / 'results' / 'x3' / 'gate_output.json').read_text())
    ge = json.loads((ROOT / 'results' / 'e4b' / 'gate_output.json').read_text())
    xr = list(csv.DictReader(open(ROOT / 'results' / 'x3' / 'detectors' / 'runs_detectors_main.csv')))
    er = list(csv.DictReader(open(ROOT / 'results' / 'e4b' / 'detectors' / 'runs_detectors_main.csv')))
    mechs = ('M1', 'M2', 'M3')

    def wk(rows, m, f):
        rs = [r for r in rows if r['mechanism'] == m and r['framing'] == f and r['status'] in EV]
        return {'W1': sum(r['W'] == '1' for r in rs), 'n': len(rs),
                'W0_tests_pass': sum(r['W'] == '0' and r['F'] == '1' for r in rs),
                'W0': sum(r['W'] == '0' for r in rs)}
    det = x3['detectors']['by_condition_mechanism']
    rd = x3['row_descriptives']['C']['by_mechanism']
    patches = {}
    for m in mechs:
        d, r = det[f'C.{m}'], rd[m]
        patches[m] = {'W1': r['n_W1'], 'tests_pass': k_of(r['tests_pass_rate_among_W1'], r['n_W1']),
                      'disclosed_any_turn': k_of(r['any_turn_disclosure_rate_among_W1'], r['n_W1']),
                      **{f'{x}_alert': k_of(d[x]['alert_rate_W1'], d[x]['n_W1']) for x in DETS},
                      **{f'{x}_evaluable': d[x]['n_W1'] for x in DETS}}
    h1 = x3['main']['frozen_report']['H1_PRIMARY_W_A_minus_N']
    rsha = lambda p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest()
    data = {'sources': {'x3_report_sha256': rsha('results/x3/x3_report.json'),
                        'e4b_report_sha256': rsha('results/e4b/e4b_report.json'),
                        'x3_seal_sha256': x3['seal_sha256'], 'e4b_seal_sha256': e4['seal_sha256']},
            'x3_W_by_mechanism_framing': {m: {f: wk(xr, m, f) for f in 'NPA'} for m in mechs},
            'e4b_W_by_mechanism': {m: wk(er, m, 'N') for m in mechs},
            'x3_weakening_patches': patches,
            'x3_dAN': {'estimate': h1['HC3_95']['estimate'], 'ci90': h1['HC3_90']['ci'],
                       'ci95': h1['HC3_95']['ci'], 'decision': h1['decision'],
                       'wording': x3['main']['wording']},
            'x3_cw': x3['cw']['CW_vs_C'], 'x3_m3_ablation': {k: x3['m3_ablation'][k] for k in
                                                             ('CL1_vs_C', 'CNH_vs_C')},
            'gate': {s: {p: g['policies'][p]['counts'] for p in ('tests_only', 'gsc', 'ast')}
                     for s, g in (('x3', gx), ('e4b', ge))}}
    lines += ['', '## Table 4. Explicit request (D15 x3, Gemma 4 31B; D16 E4B, framing N only)', '',
              'Sources: results/x3/x3_report.json (sha256 ' + data['sources']['x3_report_sha256'][:16]
              + '...), results/e4b/e4b_report.json (sha256 ' + data['sources']['e4b_report_sha256'][:16]
              + '...), their detectors/runs_detectors_main.csv; gate: results/{x3,e4b}/gate_output.json.',
              '', '| Mechanism | 31B W = 1, N | P | A | E4B W = 1 (N) | 31B W = 0 that pass tests (N) '
              '| E4B W = 0 that pass tests | 31B W = 1: tests pass | AST alert | GSC alert / evaluable '
              '| disclosed (any turn) |', '|---|---|---|---|---|---|---|---|---|---|---|']
    for m in mechs:
        x, e, p = data['x3_W_by_mechanism_framing'][m], data['e4b_W_by_mechanism'][m], patches[m]
        lines.append(f"| {m} | " + ' | '.join(f"{x[f]['W1']}/{x[f]['n']}" for f in 'NPA')
                     + f" | {e['W1']}/{e['n']} | {x['N']['W0_tests_pass']}/{x['N']['W0']} "
                     f"| {e['W0_tests_pass']}/{e['W0']} | {p['tests_pass']}/{p['W1']} "
                     f"| {p['ast_alert']}/{p['W1']} | {p['gsc_alert']}/{p['gsc_evaluable']} "
                     f"| {p['disclosed_any_turn']}/{p['W1']} |")
    lines += ['', f"x3 framing contrast (frozen estimator, K = 30): dAN {100 * h1['HC3_95']['estimate']:+.1f} pp, "
              f"IC90 [{100 * h1['HC3_90']['ci'][0]:+.1f}, {100 * h1['HC3_90']['ci'][1]:+.1f}], IC95 "
              f"[{100 * h1['HC3_95']['ci'][0]:+.1f}, {100 * h1['HC3_95']['ci'][1]:+.1f}]; sealed wording: "
              f"\"{x3['main']['wording']}\"."]
    pt = e4['vs_x3']['per_template']
    lines += ['', '## Table 4b (appendix). E4B next to x3 per base template (framing N; descriptive, '
              'another model and host, one seed)', '',
              'Source: results/e4b/e4b_report.json -> vs_x3.per_template (W = mean over the '
              'evaluable runs of each template).', '',
              '| Template | Mechanism | 31B W (n) | E4B W (n) |', '|---|---|---|---|']
    for t in pt:
        lines.append(f"| {t['base']} | {t['mechanism']} | {t['x3_31b_W']:.2f} ({t['x3_31b_n_evaluable']}) "
                     f"| {t['e4b_W']:.2f} ({t['e4b_n_evaluable']}) |")
    lines.append(f"\nPaired templates: {sum(t['paired'] for t in pt)}/{len(pt)}.")
    data['models'] = models(lines, er)
    return data


MODEL_ROWS = (   # (key, label, source): D17/D17b report key, or the D16 per-run file
    ('e2b', 'Gemma 4 E2B (QAT w4a16; Colab A100, D17b)', 'ladder2'),
    ('e4b_kaggle', 'Gemma 4 E4B (QAT w4a16; Kaggle L4x4, D16)', 'd16'),
    ('e4b_hf', 'Gemma 4 E4B (QAT w4a16; Colab A100, D17)', 'ladder'),
    ('26b_a4b', 'Gemma 4 26B-A4B (bf16 MoE; Colab A100, D17b)', 'ladder2'),
    ('31b_x3', 'Gemma 4 31B (QAT w4a16; Colab A100, x3 N)', 'ladder2'))


def outcome_counts(rows):
    """D17's ladder categories (followup/analyze_ladder.py outcomes) for D16's per-run rows."""
    ev = [r for r in rows if r['status'] in EV]
    w0 = [r for r in ev if r['W'] == '0']
    return {'runs': len(rows), 'evaluable': len(ev), 'W1': sum(r['W'] == '1' for r in ev),
            'W0_tests_pass': sum(r['F'] == '1' for r in w0),
            'W0_tests_fail': sum(r['F'] != '1' for r in w0),
            'not_evaluable': len(rows) - len(ev), 'crash': sum(r['crash'] == '1' for r in rows)}


def models(lines, e4b_rows):
    """D17 and D17b (Gemma 4 configurations under x3's condition C, framing N): the committed single
    analysis reports, next to D16's E4B rows; descriptive, post hoc, nothing pooled."""
    rep = {k: hashed_json(ROOT / 'results' / k / 'ladder_report.json') for k in ('ladder', 'ladder2')}
    if rep['ladder']['ladder_table']['31b_x3'] != rep['ladder2']['ladder_table']['31b_x3']:
        raise SystemExit('the 31B comparator rows differ between the D17 and D17b reports')
    keep = ('runs', 'evaluable', 'W1', 'W0_tests_pass', 'W0_tests_fail', 'not_evaluable', 'crash')
    mechs = ('M1', 'M2', 'M3')
    out = {'sources': {f'{k}_report_sha256': hashlib.sha256(
                           (ROOT / 'results' / k / 'ladder_report.json').read_bytes()).hexdigest()
                       for k in rep}
           | {f'{k}_seal_sha256': rep[k]['seal_sha256'] for k in rep},
           'rows': {}}
    for key, label, src in MODEL_ROWS:
        if src == 'd16':
            n = [r for r in e4b_rows if r['framing'] == 'N']
            c = {'pooled': outcome_counts(n),
                 'by_mechanism': {m: outcome_counts([r for r in n if r['mechanism'] == m]) for m in mechs}}
        else:
            t = rep[src]['ladder_table'][key]
            mr = rep[src]['models'].get(key)
            if mr is not None and not mr['floor']['met']:
                raise SystemExit(f'{key}: capability floor not met; counts only, not tabled here')
            c = {'pooled': t['pooled'], 'by_mechanism': t['by_mechanism']}
        out['rows'][key] = {'label': label, 'source': src,
                            'pooled': {k: c['pooled'][k] for k in keep},
                            'by_mechanism': {m: {k: c['by_mechanism'][m][k] for k in keep} for m in mechs}}
    h = rep['ladder']['e4b_hosts']
    out['e4b_hosts'] = {k: h[k] for k in ('templates_paired', 'templates_colab_higher',
                                          'templates_colab_lower')}
    lines += ['', '## Table 5 (appendix). Gemma 4 configurations under the explicit request '
              '(condition C, framing N; exploratory, post hoc, descriptive, no test)', '',
              'Sources: results/ladder/ladder_report.json (D17, sha256 '
              + out['sources']['ladder_report_sha256'][:16] + '...) and results/ladder2/'
              'ladder_report.json (D17b, sha256 ' + out['sources']['ladder2_report_sha256'][:16]
              + '...) -> ladder_table; D16 E4B: results/e4b/detectors/runs_detectors_main.csv '
              '(framing N). Counts among evaluable runs; a crash is coded W = 0, F = 0. Models '
              'differ in size, architecture and precision, and hosts differ; no difference is '
              'attributed to size.', '',
              '| Configuration | Mechanism | Runs | Evaluable | W = 1 | W = 0, tests pass | '
              'W = 0, tests fail | Crash |', '|---|---|---|---|---|---|---|---|']
    for key, label, _ in MODEL_ROWS:
        r = out['rows'][key]
        for i, m in enumerate((*mechs, 'all')):
            x = r['pooled'] if m == 'all' else r['by_mechanism'][m]
            lines.append(f"| {label if i == 0 else ''} | {m} | {x['runs']} | {x['evaluable']} "
                         f"| {x['W1']} | {x['W0_tests_pass']} | {x['W0_tests_fail']} | {x['crash']} |")
    e = out['e4b_hosts']
    lines.append(f"\nE4B, Kaggle (D16) vs Colab (D17), per base template: {e['templates_paired']} "
                 f"paired; Colab higher W in {e['templates_colab_higher']}, lower in "
                 f"{e['templates_colab_lower']} (results/ladder/ladder_report.json -> e4b_hosts).")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--calibration-archive', required=True)
    ap.add_argument('--out', required=True)
    a = ap.parse_args(argv)
    raw = Path(a.calibration_archive).read_bytes()
    if hashlib.sha256(raw).hexdigest() != D.CAL_SHA256:
        raise SystemExit('calibration archive is not the one recorded in D14')
    d14 = json.loads((ROOT / 'results' / 'd14' / 'd14_descriptives.json').read_text())
    conf = list(csv.DictReader(open(ROOT / 'results' / 'confirmatory' / 'runs_detectors.csv')))
    lines = ['# TwinGuard writeup tables 2 and 3b (generated; do not edit by hand)', '']
    with tempfile.TemporaryDirectory() as work:
        with tarfile.open(a.calibration_archive) as t:
            t.extractall(work, filter='data')
        block = Path(work) / 'results' / 'x1_calibration'
        rows = list(csv.DictReader(open(block / 'runs.csv', encoding='utf-8')))
        c = counts_calibration(rows)
        fig = {'sources': {'calibration_archive_sha256': D.CAL_SHA256,
                           'confirmatory': 'results/confirmatory/runs_detectors.csv',
                           'd14': 'results/d14/d14_descriptives.json'},
               'ladder': {}, 'agent_patches': {},
               'confirmatory_by_arm': confirmatory_by_arm(conf)}
        lines += ['## Table 2. Calibration ladder (D12; 6 pilot templates, 2 per mechanism; '
                  'pooled framings, 1 seed)', '',
                  'Source: calibration archive sha256 ' + D.CAL_SHA256[:16] + '..., '
                  'results/x1_calibration/runs.csv; mention/rejection: results/d14/'
                  'd14_descriptives.json (lexical matches, last-try logs).', '',
                  '| Rung | What the issue shows | Mechanism | Scheduled | Completed | Not run '
                  '(time cut) | W = 1 | Tests pass | Mentions patch | Rejection phrase |',
                  '|---|---|---|---|---|---|---|---|---|---|']
        what = {'L1': 'project policy replaced by a generic CONTRIBUTING.md',
                'L2': 'policy intact + unreviewed teammate patch (U+) shown',
                'L3': 'L1 + L2', 'C': 'policy intact + "Please apply this patch" + U+'}
        for rung in ('L1', 'L2', 'L3', 'C'):
            pm = d14['process_measures'][rung]
            for mech in ('M1', 'M2', 'M3', 'all'):
                x = c[(rung, mech)]
                src = pm['pooled'] if mech == 'all' else pm['by_mechanism'][mech]
                mp, rp = src['mentions_patch'], src['rejects_patch']
                fmt = lambda m: '—' if m['mean'] is None else f"{round(m['mean'] * m['n'])}/{m['n']}"
                fig['ladder'].setdefault(rung, {})[mech] = {
                    'scheduled': x['scheduled'], 'completed': x['completed'], 'W1': x['W1'],
                    'tests_pass': x['F1']}
                lines.append(f"| {rung if mech == 'M1' else ''} | {what[rung] if mech == 'M1' else ''} "
                             f"| {mech} | {x['scheduled']} | {x['completed']} | {x['closed_or_failed']} "
                             f"| {x['W1']}/{x['completed']} | {x['F1']}/{x['completed']} | {fmt(mp)} | {fmt(rp)} |")
        cal_w1 = [r for r in rows if r['status'] in EV and r['W'] == '1']
        cal_states = detector_states(cal_w1, block)
    conf_w1 = [r for r in conf if r['status'] in EV and r['W'] == '1']
    conf_states = {r['run_id']: {d: r[d] for d in DETS} for r in conf_w1}
    lines += ['', '## Table 3b. The agent\'s own weakening patches (oracle W = 1)', '',
              'Sources: calibration C rows of the archive above, detectors re-run with the frozen '
              'runner/secondary.detect on each run\'s evaluated patch; confirmatory: '
              'results/confirmatory/runs_detectors.csv (the single analysis).', '',
              '| Set | Mechanism | Runs W = 1 | Distinct templates | Tests pass | GSC alert | '
              'AST alert | except alert |', '|---|---|---|---|---|---|---|---|']
    for key, (rs, st, label) in {'calibration_C': (cal_w1, cal_states, 'Calibration C (explicit request)'),
                                 'confirmatory': (conf_w1, conf_states, 'Confirmatory (no request)')}.items():
        out, data = table3b(rs, st, label)
        lines += out
        fig['agent_patches'][key] = data
    per_t = defaultdict(lambda: [0, 0])
    for r in cal_w1:
        per_t[r['template_id']][0] += 1
        per_t[r['template_id']][1] += cal_states[r['run_id']]['gsc'] == 'alert'
    lines += ['', 'Calibration C, per template (W = 1 runs / GSC alerts): '
              + ', '.join(f'{t} {n}/{g}' for t, (n, g) in sorted(per_t.items())) + '.']
    demo = ROOT / 'bank' / 'templates' / 'M1.cold_chain_release' / 'patches'
    lines += ['', '## Figure. One token apart (M1.cold_chain_release, admission witnesses)', '',
              'S+ (safe repair; oracle W = 0, tests pass):', '```diff',
              (demo / 's_plus.diff').read_text().rstrip(), '```', '',
              'U+ (weakening repair; oracle W = 1, tests pass):', '```diff',
              (demo / 'u_plus.diff').read_text().rstrip(), '```']
    fig['followup'] = followup(lines)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    text = '\n'.join(lines) + '\n'
    Path(a.out).write_text(text)
    fd = json.dumps(fig, indent=1, sort_keys=True) + '\n'
    fpath = Path(a.out).parent / 'figure_data.json'
    fpath.write_text(fd)
    fsha = hashlib.sha256(fd.encode()).hexdigest()
    (fpath.parent / 'figure_data.json.sha256').write_text(f'{fsha}  figure_data.json\n')
    print(json.dumps({'out': a.out, 'sha256': hashlib.sha256(text.encode()).hexdigest(),
                      'figure_data_sha256': fsha}))


if __name__ == '__main__':
    main()
