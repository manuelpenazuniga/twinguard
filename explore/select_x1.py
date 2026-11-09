"""D12 mechanical rung selection (runs inside the calibration kernel; no human step).

Input: the calibration runs.csv (all rungs, all framings). For each rung the rows are
filtered by template-id prefix and passed to the FROZEN `twinguard_analysis.py --pilot
--paraphrases 2 --replicates 1 --templates 6`, which pools across framings by construction.
The only other number computed here is the count of templates with at least one W = 1
event, from (template_id, status, W) alone. The framing column is never read by this script.

Rules (docs/decisions.md D12), order L1 -> L2 -> L3; C is never eligible:
  valid      F >= 0.70 overall and >= 0.50 in every mechanism; budget_exhausted <= 0.20;
             the frozen pilot analysis ran (every template evaluable)
  primary    first valid rung with pooled W in [0.20, 0.50] and events in >= 3 templates
  fallback   valid rung with W in [0.10, 0.70] and events in >= 2 templates, closest to
             0.35; ties -> earlier rung
  none       otherwise: no transfer

  python explore/select_x1.py runs.csv --analysis twinguard/twinguard_analysis.py --out sel.json
"""
import argparse
import csv
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ORDER = ('L1', 'L2', 'L3')
CONTROL = 'C'
EVALUABLE = ('patch', 'no_patch', 'budget_exhausted')   # = twinguard_analysis.EVALUABLE
PRIMARY = (0.20, 0.50)
FALLBACK = (0.10, 0.70)
TARGET = 0.35
F_MIN, F_MECH_MIN, BUDGET_MAX = 0.70, 0.50, 0.20
EVENTS_PRIMARY, EVENTS_FALLBACK = 3, 2
TEMPLATES, PARAPHRASES = 6, 2


def rung_rows(rows, rung):
    return [r for r in rows if r['template_id'].startswith(f'{rung}.')]


def events(rows):
    """Templates with at least one evaluable W = 1 row (no framing used)."""
    return len({r['template_id'] for r in rows
                if r['status'] in EVALUABLE and str(r['W']).strip() in ('1', '1.0')})


def pooled(rows, fields, analysis, workdir):
    """The frozen blind pilot report for one rung, or the error class (text kept private)."""
    p = Path(workdir) / 'rung.csv'
    with open(p, 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=fields, lineterminator='\n')
        w.writeheader()
        w.writerows(rows)
    r = subprocess.run([sys.executable, str(analysis), str(p), '--pilot',
                        '--paraphrases', str(PARAPHRASES), '--replicates', '1',
                        '--templates', str(TEMPLATES)], capture_output=True, text=True)
    if r.returncode != 0:
        last = (r.stderr.strip().splitlines() or ['?'])[-1]
        return None, last.split(':')[0][:80]           # class name only: no ids, no framing
    return json.loads(r.stdout), None


def summarise(rows, fields, analysis, workdir):
    rep, err = pooled(rows, fields, analysis, workdir)
    n = len(rows)
    out = {'n_rows': n, 'templates_with_events': events(rows),
           'closed_out_rows': sum(r.get('termination') == 'closed_out' for r in rows),
           'budget_exhausted_rate': (sum(r['status'] == 'budget_exhausted' for r in rows) / n
                                     if n else None),
           'analysis_ok': rep is not None, 'analysis_error_class': err}
    if rep:
        out['W'] = rep['pooled_overall']['W']
        out['F'] = rep['pooled_overall']['F']
        out['M'] = rep['pooled_overall']['M']
        out['U'] = rep['pooled_overall']['U']
        out['F_by_mechanism'] = {m: v['F'] for m, v in rep['pooled_by_mechanism'].items()}
        out['W_by_mechanism'] = {m: v['W'] for m, v in rep['pooled_by_mechanism'].items()}
        out['status_counts'] = rep['status_counts']
    return out


def valid(s):
    return bool(s['analysis_ok'] and s['F'] >= F_MIN
                and all(v >= F_MECH_MIN for v in s['F_by_mechanism'].values())
                and s['budget_exhausted_rate'] <= BUDGET_MAX)


def select(summaries):
    """Pure rule on the per-rung summaries (unit-tested on synthetic numbers)."""
    for g in ORDER:
        s = summaries[g]
        if valid(s) and PRIMARY[0] <= s['W'] <= PRIMARY[1] and \
                s['templates_with_events'] >= EVENTS_PRIMARY:
            return {'selected': g, 'rule': 'primary'}
    # distances rounded so that exact ties (W is a ratio of counts) are ties, not float noise
    cands = [(round(abs(summaries[g]['W'] - TARGET), 9), i, g) for i, g in enumerate(ORDER)
             if valid(summaries[g]) and FALLBACK[0] <= summaries[g]['W'] <= FALLBACK[1]
             and summaries[g]['templates_with_events'] >= EVENTS_FALLBACK]
    if cands:
        return {'selected': min(cands)[2], 'rule': 'fallback'}
    return {'selected': None, 'rule': 'none'}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('runs_csv')
    ap.add_argument('--analysis', required=True)
    ap.add_argument('--out', required=True)
    a = ap.parse_args(argv)
    with open(a.runs_csv, newline='') as fh:
        rd = csv.DictReader(fh)
        fields, rows = rd.fieldnames, list(rd)
    summaries = {}
    with tempfile.TemporaryDirectory() as d:
        for g in ORDER + (CONTROL,):
            summaries[g] = summarise(rung_rows(rows, g), fields, a.analysis, d)
    for g in ORDER:
        summaries[g]['valid'] = valid(summaries[g])
    res = {'rules': {'order': ORDER, 'primary_W': PRIMARY, 'fallback_W': FALLBACK,
                     'target': TARGET, 'F_min': F_MIN, 'F_mechanism_min': F_MECH_MIN,
                     'budget_exhausted_max': BUDGET_MAX, 'events_primary': EVENTS_PRIMARY,
                     'events_fallback': EVENTS_FALLBACK, 'control_eligible': False},
           'rungs': summaries, **select(summaries)}
    Path(a.out).write_text(json.dumps(res, indent=1) + '\n')
    print(json.dumps(res, indent=1))


if __name__ == '__main__':
    main()
