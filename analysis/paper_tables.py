"""Writeup tables 2 and 3b (WP14), next to resource/tables.py (table 1 and the witness table).
Every number is counted from a results file and printed with its source; nothing is estimated.

  Table 2  D12 calibration ladder (pilot templates, pooled N/P/A, framing never grouped): per rung
           and mechanism, scheduled / completed / closed-out runs, W = 1, tests passing (F = 1),
           and the lexical patch-mention and rejection matches (D14 descriptive 1).
  Table 3b The agent's own weakening patches (oracle W = 1): calibration C and confirmatory, per
           mechanism: runs, distinct templates, tests passing, and alerts of the frozen detectors.
  Figure   The M1 example: the S+ and U+ witness diffs of the first pilot M1 template.

  python analysis/paper_tables.py --calibration-archive x1_cal_out/results_sealed.tar.gz \
      --out results/paper/tables_2_3b.md
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
    out = []
    for key in ('M1', 'M2', 'M3', 'all'):
        if key not in t:
            continue
        c = t[key]
        out.append(f"| {label} | {key} | {c['runs']} | {len(tmpl[key])} | {c['F1']}/{c['runs']} | "
                   + ' | '.join(f"{c[d]}/{c['runs']}" for d in DETS) + ' |')
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
    lines += table3b(cal_w1, cal_states, 'Calibration C (explicit request)')
    lines += table3b(conf_w1, conf_states, 'Confirmatory (no request)')
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
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    text = '\n'.join(lines) + '\n'
    Path(a.out).write_text(text)
    print(json.dumps({'out': a.out, 'sha256': hashlib.sha256(text.encode()).hexdigest()}))


if __name__ == '__main__':
    main()
