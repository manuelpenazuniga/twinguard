"""Merge the confirmatory shards and report truncation (protocol 7.4, Annex A; WP11).

Each shard (one chain of Kaggle sessions) leaves results/confirmatory/ inside its final sealed
archive. This tool, run at decoding time on the extracted shard directories:

  * checks every shard against the freeze manifest (shard id, schedule digest, freeze hash in
    its session log) and that the union of rows is exactly the frozen schedule, once each;
  * checks one value of model_id, model_revision, harness_commit, oracle_commit and
    environment_id over all rows (7.4);
  * classifies every sector block as complete, partial or not_started (rows closed out at the
    deadline are the time cut) and states whether the analysis must run with --exploratory;
  * writes the merged runs.csv and truncation_report.json (framing-free).

  python runner/merge.py --freeze freeze/manifest.json --out results/confirmatory \
      SHARD_DIR [SHARD_DIR ...]
"""
import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runner.runner import COLUMNS, schedule, schedule_digest, shard_runs  # noqa: E402

SINGLE = ('model_id', 'model_revision', 'harness_commit', 'oracle_commit', 'environment_id')


def closed_out_ids(shard_dir):
    ids = set()
    for line in (Path(shard_dir) / 'attempts.jsonl').read_text(encoding='utf-8').splitlines():
        if line.strip():
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get('final') and r.get('closed_out'):
                ids.add(r['run_id'])
    return ids


def merge(freeze_path, shard_dirs, bank=None, spec=None):
    freeze_text = Path(freeze_path).read_bytes()
    freeze_sha = hashlib.sha256(freeze_text).hexdigest()
    fz = json.loads(freeze_text)
    d = fz['design']
    full = schedule(bank or ROOT / 'bank' / 'templates', spec or ROOT / 'bank' / 'spec_matrix.csv',
                    'confirmatory', d['S'], fz['seeds']['order_seed'])
    if schedule_digest(full) != d['schedule_sha256']:
        raise SystemExit('the schedule rebuilt here differs from the frozen schedule')
    n = len(d['shards'])
    rows, closed, seen_shards = [], set(), set()
    for sd in map(Path, shard_dirs):
        man = json.loads((sd / 'manifest.json').read_text())
        shard = man.get('shard')
        if shard not in d['shards'] or shard in seen_shards:
            raise SystemExit(f'{sd}: unknown or repeated shard {shard!r}')
        seen_shards.add(shard)
        i = int(shard.split('/')[0])
        if man['schedule_sha256'] != d['shards'][shard]['schedule_sha256'] or \
                schedule_digest(shard_runs(full, (i, n))) != man['schedule_sha256']:
            raise SystemExit(f'{sd}: shard schedule differs from the freeze')
        sessions = [json.loads(x) for x in (sd / 'sessions.jsonl').read_text().splitlines() if x.strip()]
        if [s['session'] for s in sessions] != list(range(1, len(sessions) + 1)) or \
                any(s['freeze_sha256'] != freeze_sha or s['shard'] != shard for s in sessions):
            raise SystemExit(f'{sd}: session chain does not match the freeze')
        rows += list(csv.DictReader(open(sd / 'runs.csv', encoding='utf-8')))
        closed |= closed_out_ids(sd)
    if seen_shards != set(d['shards']):
        raise SystemExit(f'missing shards: {sorted(set(d["shards"]) - seen_shards)}')

    ids = [r['run_id'] for r in rows]
    if len(ids) != len(set(ids)):
        raise SystemExit('duplicate run_id across shards')
    if set(ids) != {r['run_id'] for r in full}:
        raise SystemExit('merged rows are not exactly the frozen schedule')
    for col in SINGLE:
        vals = {r[col] for r in rows}
        if len(vals) != 1 or '' in vals:
            raise SystemExit(f'{col}: expected one non-empty value, got {sorted(vals)}')

    order = {r['run_id']: r['order'] for r in full}
    rows.sort(key=lambda r: order[r['run_id']])
    blocks = []
    for fam in d['block_order']:
        b = [r for r in rows if r['family'] == fam]
        cut = sum(1 for r in b if r['run_id'] in closed)
        state = 'complete' if cut == 0 else ('not_started' if cut == len(b) else 'partial')
        blocks.append({'family': fam, 'templates': sorted({r['template_id'] for r in b}),
                       'scheduled': len(b), 'closed_out': cut, 'state': state,
                       'status_counts': {s: sum(1 for r in b if r['status'] == s)
                                         for s in sorted({r['status'] for r in b})}})
    complete = [b for b in blocks if b['state'] == 'complete']
    report = {'freeze_sha256': freeze_sha, 'K_scheduled': d['K'],
              'K_in_complete_blocks': 3 * len(complete),
              'blocks': blocks, 'closed_out_runs': len(closed),
              'exploratory_required': len(complete) < len(blocks),
              'analysis_flag': '--exploratory' if len(complete) < len(blocks) else '',
              'note': 'K evaluable per contrast is reported by twinguard_analysis.py'}
    return rows, report


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--freeze', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('shards', nargs='+')
    a = ap.parse_args(argv)
    rows, report = merge(a.freeze, a.shards)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    with open(out / 'runs.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, '') for k in COLUMNS})
    (out / 'truncation_report.json').write_text(json.dumps(report, indent=1))
    print(json.dumps({k: report[k] for k in ('K_scheduled', 'K_in_complete_blocks',
                                             'closed_out_runs', 'analysis_flag')}))


if __name__ == '__main__':
    main()
