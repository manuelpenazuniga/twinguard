"""D14's three declared descriptives (exploratory, CPU; no claim on W or A-N; framings never
grouped). Fixed in docs/decisions.md D14 before the confirmatory was decoded.

  1. Calibration process measures: the sealed explore/process_x1.measures (imported, unchanged)
     on the last-try logs of the completed D12 calibration runs, pooled by rung (L1, L2, L3, C)
     and by mechanism; patch mention/rejection only for the rungs exposing u_plus.diff (L2, L3,
     C). Denominators and runs without a log reported.
  2. Detectors on the agent's own patches: the frozen detectors (runner/secondary.detect: GSC
     depth 2 plus the fixed depths 1 and 3, the AST baseline, except_local) on the final patches
     of the same runs (bound to the evaluated patch by its sha256), by rung and mechanism:
     detection among oracle W = 1 runs and alarm rate among W = 0 runs, as counts.
  3. Fixed demonstration of the instrument: for each mechanism, the first pilot template in
     sorted id order; its S+, U+ and alternative-safe witnesses with the functional tests and
     the oracle verdicts, read from the frozen admission record (bank/admission/<id>.json).
     Constructed witnesses; no selection by results.
The framing is read only to render each run's own repository for the detectors.

  python analysis/d14_descriptives.py --calibration-archive x1_cal_out/results_sealed.tar.gz \
      --out results/d14
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
from explore import process_x1 as PX  # noqa: E402  (sealed with D12)
from runner import secondary as S  # noqa: E402  (frozen)

CAL_SHA256 = '10cec81c56e1a98e74578e33522fbf0c48875cbb0a1f444964e92dc371e74c1f'   # D14
X1_BANK = ROOT / 'explore' / 'bank_x1' / 'templates'
EXPOSING = ('L2', 'L3', 'C')
D14_DETECTORS = ('gsc', 'ast', 'except_local')


def sha(b):
    return hashlib.sha256(b).hexdigest()


def completed(rows):
    return [r for r in rows if r['status'] in S.EVALUABLE]


def process_measures(rows, logs):
    groups = defaultdict(list)
    missing = defaultdict(int)
    for r in completed(rows):
        rung = r['template_id'].split('.')[0]
        meta = json.loads((X1_BANK / r['template_id'] / 'template.json').read_text())
        log = PX.last_log(logs, r['run_id'])
        if log is None:
            missing[rung] += 1
            continue
        m = PX.measures(log, Path(meta['monitor_module']).name, rung in EXPOSING)
        groups[(rung, 'all')].append(m)
        groups[(rung, r['mechanism'])].append(m)

    def summ(ms):
        out = {}
        for k in PX.MEASURES:
            v = [m[k] for m in ms if m.get(k) is not None]
            out[k] = {'mean': (sum(v) / len(v)) if v else None, 'n': len(v)}
        return out
    res = {}
    for (rung, mech), ms in sorted(groups.items()):
        res.setdefault(rung, {'n_runs_with_log': 0, 'n_without_log': missing[rung],
                              'by_mechanism': {}})
        if mech == 'all':
            res[rung]['n_runs_with_log'] = len(ms)
            res[rung]['pooled'] = summ(ms)
        else:
            res[rung]['by_mechanism'][mech] = summ(ms)
    return res


def one(job):
    run_id, template_id, framing, patch_text = job
    meta = json.loads((X1_BANK / template_id / 'template.json').read_text())
    with tempfile.TemporaryDirectory(prefix='tg_d14_') as work:
        before, after, err = S.patched_pair(template_id, framing, patch_text, work, bank=X1_BANK)
        if err is not None:
            return run_id, {c: 'not_evaluable' for c in S.DETECTORS}
        return run_id, S.detect(before, after, meta)[0]


def detectors(rows, block_dir, workers):
    from concurrent.futures import ProcessPoolExecutor
    finals = S.final_events([block_dir])
    ev = completed(rows)
    jobs = [(r['run_id'], r['template_id'], r['framing'], S.patch_of(finals, r['run_id']))
            for r in ev]
    with ProcessPoolExecutor(workers) as ex:
        states = dict(ex.map(one, jobs, chunksize=2))
    counts = defaultdict(lambda: defaultdict(int))
    for r in ev:
        rung, mech, W = r['template_id'].split('.')[0], r['mechanism'], r['W']
        for key in ((rung, 'all'), (rung, mech)):
            for c in S.DETECTORS:
                st = states[r['run_id']][c]
                counts[key][f'{c}|W{W}|{st}'] += 1
            counts[key][f'n_W{W}'] += 1
    out = {}
    for (rung, mech), c in sorted(counts.items()):
        d = {'n_W1': c['n_W1'], 'n_W0': c['n_W0']}
        for det in S.DETECTORS:
            d[det] = {f'W{w}': {s: c[f'{det}|W{w}|{s}'] for s in ('alert', 'no_alert', 'not_evaluable')}
                      for w in (1, 0)}
        out.setdefault(rung, {})[mech] = d
    return {'runs': len(jobs), 'declared_detectors': list(D14_DETECTORS),
            'also_reported': [d for d in S.DETECTORS if d not in D14_DETECTORS],
            'by_rung': out}


def demonstration():
    spec = list(csv.DictReader(open(ROOT / 'bank' / 'spec_matrix.csv')))
    out = {}
    for mech in ('M1', 'M2', 'M3'):
        tid = sorted(r['template_id'] for r in spec if r['split'] == 'pilot' and r['mechanism'] == mech)[0]
        a = json.loads((ROOT / 'bank' / 'admission' / f'{tid}.json').read_text())['criteria']
        wit = {'s_plus': a['3_s_plus']['runs'], 'u_plus': a['4_u_plus']['runs'],
               'alt_safe': a['6_oracles']['alt_safe_runs']}
        out[mech] = {'template_id': tid, 'witnesses': {
            k: {f: {'tests_passed': v[f]['tests']['passed'], 'tests_summary': v[f]['tests']['summary'],
                    'oracle_W': v[f]['oracle']['W'], 'oracle_checks': v[f]['oracle']['checks']}
                for f in sorted(v)} for k, v in wit.items()},
            'source': f'bank/admission/{tid}.json (frozen admission record)'}
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--calibration-archive', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--workers', type=int, default=8)
    a = ap.parse_args(argv)
    if not (ROOT / 'results' / 'confirmatory' / 'analysis_hashes.json').exists():
        raise SystemExit('D14 descriptives run only after the authorized decoding')
    raw = Path(a.calibration_archive).read_bytes()
    if sha(raw) != CAL_SHA256:
        raise SystemExit('calibration archive is not the one recorded in D14')
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as work:
        with tarfile.open(a.calibration_archive) as t:
            t.extractall(work, filter='data')
        block = Path(work) / 'results' / 'x1_calibration'
        rows = list(csv.DictReader(open(block / 'runs.csv', encoding='utf-8')))
        res = {'d14': 'docs/decisions.md D14 (declared before decoding)',
               'calibration_archive_sha256': CAL_SHA256,
               'rows': len(rows), 'completed_runs': len(completed(rows)),
               'process_measures': process_measures(rows, block / 'logs'),
               'detectors_on_agent_patches': detectors(rows, block, a.workers),
               'instrument_demonstration': demonstration(),
               'grouping': 'rung and mechanism; framings never grouped'}
    text = json.dumps(res, indent=1, sort_keys=True) + '\n'
    (out / 'd14_descriptives.json').write_text(text)
    (out / 'd14_descriptives.json.sha256').write_text(f'{sha(text.encode())}  d14_descriptives.json\n')
    print(json.dumps({'completed_runs': res['completed_runs'], 'sha256': sha(text.encode())}))


if __name__ == '__main__':
    main()
