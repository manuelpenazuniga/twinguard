"""D15 (x3) descriptive (a): the frozen secondary detectors on the agent's own x3 patches.

For every evaluable x3 row (main C rows of complete sectors, CW rows of complete templates) the
run's final patch, bound to the evaluated one by its sha256 (runner/secondary.patch_of), is
applied to a clean render of its own template and framing and the five frozen detectors of
runner/secondary.detect run on the pair (GSC depth 1/2/3, AST and `except` baselines). Then the
frozen twinguard/twinguard_gate.py runs once on the main C rows (pooled, framings weighted
equally, GSC vs AST). Reported per condition and mechanism, never per framing: alert rates
among W = 1 and among W = 0 rows. Detectors never define W and read neither W nor the label.

  (called by followup/analyze_x3.py; no separate run)
"""
import csv
import json
import subprocess
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from runner import secondary as S  # noqa: E402  (frozen with D12)

X3_BANK = ROOT / 'followup' / 'bank_x3' / 'templates'


def one(job):
    run_id, template_id, framing, patch_text = job
    meta = json.loads((X3_BANK / template_id / 'template.json').read_text())
    with tempfile.TemporaryDirectory(prefix='tg_x3det_') as work:
        before, after, err = S.patched_pair(template_id, framing, patch_text, work, bank=X3_BANK)
        if err is not None:
            return run_id, {c: 'not_evaluable' for c in S.DETECTORS}, {'apply_error': str(err)[:300]}
        states, why = S.detect(before, after, meta)
        return run_id, states, why


def wval(x):
    try:
        return str(int(float(x)))
    except (TypeError, ValueError):
        return ''


def rates(rows):
    """Alert rate of each detector among W = 1 and W = 0 rows (evaluable detector states only)."""
    out = {}
    for c in S.DETECTORS:
        d = {}
        for w in ('1', '0'):
            st = [r[c] for r in rows if wval(r['W']) == w and r[c] in ('alert', 'no_alert')]
            d[f'alert_rate_W{w}'] = (sum(s == 'alert' for s in st) / len(st)) if st else None
            d[f'n_W{w}'] = len(st)
        d['not_evaluable'] = sum(r[c] == 'not_evaluable' for r in rows)
        out[c] = d
    return out


def run(rows, block_dirs, out_dir, workers=8):
    """rows: list of runs.csv dicts (each with a 'condition' key added); block_dirs: the block
    directories whose attempts.jsonl and patches/ hold the final events."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    finals = S.final_events(block_dirs)
    ev = [r for r in rows if r['status'] in S.EVALUABLE]
    jobs = [(r['run_id'], r['template_id'], r['framing'], S.patch_of(finals, r['run_id']))
            for r in ev]
    with ProcessPoolExecutor(workers) as ex:
        res = {rid: (s, w) for rid, s, w in ex.map(one, jobs, chunksize=4)}
    with open(out_dir / 'detectors.jsonl', 'w', encoding='utf-8') as f:
        for rid in sorted(res):
            f.write(json.dumps({'run_id': rid, 'states': res[rid][0], 'reasons': res[rid][1]},
                               default=str) + '\n')
    full = [{**r, **{c: res.get(r['run_id'], ({}, {}))[0].get(c, '') for c in S.DETECTORS}}
            for r in ev]
    summary = {'runs': len(jobs), 'by_condition': {}, 'by_condition_mechanism': {}}
    for cond in sorted({r['condition'] for r in full}):
        sub = [r for r in full if r['condition'] == cond]
        summary['by_condition'][cond] = rates(sub)
        for mech in sorted({r['mechanism'] for r in sub}):
            summary['by_condition_mechanism'][f'{cond}.{mech}'] = rates(
                [r for r in sub if r['mechanism'] == mech])
    main = [r for r in full if r['condition'] == 'C']
    if main:
        cols = [k for k in main[0] if k != 'condition']
        with open(out_dir / 'runs_detectors_main.csv', 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction='ignore')
            w.writeheader()
            w.writerows(main)
        cmd = [sys.executable, str(ROOT / 'twinguard' / 'twinguard_gate.py'),
               str(out_dir / 'runs_detectors_main.csv'), '--detectors', *S.DETECTORS,
               '--compare', 'gsc', 'ast']
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT / 'twinguard'),
                           timeout=S.GATE_TIMEOUT_S)
        summary['gate_rc'] = r.returncode
        try:
            summary['gate'] = json.loads(r.stdout)
        except json.JSONDecodeError:
            summary['gate_stdout_tail'] = r.stdout[-2000:]
            summary['gate_stderr_tail'] = r.stderr[-2000:]
    (out_dir / 'detectors_summary.json').write_text(json.dumps(summary, indent=1, default=str))
    return summary
