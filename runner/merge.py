"""Merge the confirmatory shards and report truncation (protocol 7.4, Annex A; WP11).

Each shard (one chain of Kaggle sessions) leaves results/confirmatory/ inside its final sealed
archive. This tool, run at decoding time on the extracted shard directories:

  * checks every shard against the freeze manifest: shard id and schedule digest, a complete
    session chain under the frozen manifest hash, all sessions on one code commit whose
    freeze/manifest.json IS this manifest;
  * checks every row against the frozen schedule cell by cell (template, family, mechanism,
    framing, paraphrase, replicate, seed), in its own shard, once; one final event per row in
    attempts.jsonl with the same identity; no unreadable events;
  * rebuilds every row from its final event and the blind adjudications (each event checked
    for internal consistency) and requires runs.csv to be exactly those rows; checks the
    session parents;
  * checks model_id, model_revision and environment_id against the freeze, and
    harness_commit = oracle_commit = the sessions' code commit (7.4);
  * classifies every sector block as complete, partial or not_started (rows closed out at the
    deadline are the time cut; not_started = closed out without any started try), per shard
    and in the published order, and states whether the analysis must run with --exploratory;
  * writes the merged runs.csv and truncation_report.json (framing-free).

  python runner/merge.py --freeze freeze/manifest.json --out results/confirmatory \
      SHARD_DIR [SHARD_DIR ...]

runner/analyze.py is the only sanctioned way to run the confirmatory analysis: it calls this
merge and passes --exploratory whenever the report requires it.
"""
import argparse
import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runner.runner import (COLUMNS, needs_adjudication, outcome, schedule,  # noqa: E402
                           schedule_digest, shard_runs)

IDENTITY = ('template_id', 'family', 'mechanism', 'split', 'framing', 'issue_paraphrase',
            'replicate_id', 'seed')
OUTCOME = ('status', 'W', 'F', 'M', 'crash')


def cell(v):
    """A value as runs.csv holds it (the runner writes None as an empty field)."""
    return '' if v is None else str(v)


def fail(msg):
    raise SystemExit(f'merge refused: {msg}')


def events(shard_dir):
    return jsonl(Path(shard_dir) / 'attempts.jsonl', 'event')


def jsonl(path, what):
    out = []
    for i, line in enumerate(Path(path).read_text(encoding='utf-8').splitlines(), 1):
        if line.strip():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                fail(f'{path}: unreadable {what} at line {i}')
    return out


def session_chain(sd, shard, freeze_sha):
    """Sessions 1..n of one shard under this freeze; session 1 starts empty, every later
    session names the sealed archive it resumed (its parent), each parent once."""
    sessions = jsonl(sd / 'sessions.jsonl', 'session entry')
    if not sessions or [s.get('session') for s in sessions] != list(range(1, len(sessions) + 1)) \
            or any(s.get('freeze_sha256') != freeze_sha or s.get('shard') != shard
                   for s in sessions):
        fail(f'{sd}: session chain does not match the freeze')
    parents = [s.get('parent_sha256') for s in sessions]
    if parents[0] is not None or any(not p or len(str(p)) != 64 for p in parents[1:]) \
            or len(set(parents[1:])) != len(parents) - 1:
        fail(f'{sd}: session chain has a missing, extra or repeated parent archive')
    return sessions


def rebuild(sd, finals, adj):
    """The rows the runner's events and blind adjudications imply (runner.rows()), with every
    final event checked for internal consistency: outcome = f(summary, evaluation), rows
    without an evaluation are infrastructure failures, the close-out mark agrees with the row."""
    if set(adj) - set(finals):
        fail(f'{sd}: adjudication for a run without a final event')
    out = {}
    for rid, rec in finals.items():
        row, ev = dict(rec['row']), rec.get('evaluation')
        if ev is None:
            if row.get('status') != 'infra_failed' or any(row.get(k) is not None
                                                         for k in OUTCOME[1:]):
                fail(f'{sd}: a row without evaluation is not an infrastructure failure')
        else:
            if bool(rec.get('needs_adjudication')) != needs_adjudication(ev):
                fail(f'{sd}: needs_adjudication flag disagrees with the evaluation')
            if tuple(row.get(k) for k in OUTCOME) != outcome(rec.get('summary') or {}, ev):
                fail(f'{sd}: row outcome disagrees with its evaluation')
            if rec.get('needs_adjudication') and rid in adj:
                row.update(zip(OUTCOME, outcome(rec.get('summary') or {}, ev, adj[rid])))
        if bool(rec.get('closed_out')) != (row.get('termination') == 'closed_out'):
            fail(f'{sd}: close-out mark of the event and termination of the row disagree')
        if rec.get('closed_out') and ev is not None:
            fail(f'{sd}: a closed-out run has an evaluation')
        out[rid] = row
    return out


def manifest_at(commit, repo=None):
    try:
        return subprocess.run(['git', 'show', f'{commit}:freeze/manifest.json'], cwd=repo or ROOT,
                              capture_output=True, check=True).stdout
    except subprocess.CalledProcessError:
        fail(f'commit {commit} has no freeze/manifest.json in this repository')


def merge(freeze_path, shard_dirs, bank=None, spec=None, check_commit=True, repo=None):
    freeze_text = Path(freeze_path).read_bytes()
    freeze_sha = hashlib.sha256(freeze_text).hexdigest()
    fz = json.loads(freeze_text)
    d = fz['design']
    full = schedule(bank or ROOT / 'bank' / 'templates', spec or ROOT / 'bank' / 'spec_matrix.csv',
                    'confirmatory', d['S'], fz['seeds']['order_seed'])
    if schedule_digest(full) != d['schedule_sha256']:
        fail('the schedule rebuilt here differs from the frozen schedule')
    frozen = {r['run_id']: r for r in full}
    n = len(d['shards'])
    rows, closed, started, seen, commits, by_shard = [], set(), set(), set(), set(), {}
    for sd in map(Path, shard_dirs):
        man = json.loads((sd / 'manifest.json').read_text())
        shard = man.get('shard')
        if shard not in d['shards'] or shard in seen:
            fail(f'{sd}: unknown or repeated shard {shard!r}')
        seen.add(shard)
        mine = shard_runs(full, (int(shard.split('/')[0]), n))
        if man['schedule_sha256'] != d['shards'][shard]['schedule_sha256'] or \
                schedule_digest(mine) != man['schedule_sha256']:
            fail(f'{sd}: shard schedule differs from the freeze')
        sessions = session_chain(sd, shard, freeze_sha)
        commits |= {s.get('code_commit') for s in sessions}

        shard_rows = list(csv.DictReader(open(sd / 'runs.csv', encoding='utf-8')))
        ids = [r['run_id'] for r in shard_rows]
        if len(ids) != len(set(ids)) or set(ids) != {r['run_id'] for r in mine}:
            fail(f'{sd}: rows are not exactly this shard\'s frozen runs')
        finals = {}
        for e in events(sd):
            if e.get('event') == 'start':
                started.add(e['run_id'])
            if e.get('final'):
                if e['run_id'] in finals:
                    fail(f'{sd}: two final events for one run')
                finals[e['run_id']] = e
                if e.get('closed_out'):
                    closed.add(e['run_id'])
        if set(finals) != set(ids):
            fail(f'{sd}: final events and rows differ')
        adj_path = sd / 'adjudications.jsonl'
        adj = {d['run_id']: d for d in (jsonl(adj_path, 'adjudication')
                                        if adj_path.exists() else [])}
        implied = rebuild(sd, finals, adj)
        for r in shard_rows:
            f, ev = frozen[r['run_id']], implied[r['run_id']]
            for k in IDENTITY:
                if str(r[k]) != str(f[k]) or cell(ev[k]) != str(f[k]):
                    fail(f'{sd}: {k} of a row differs from the frozen schedule')
            if any(r.get(k, '') != cell(ev.get(k)) for k in COLUMNS):
                fail(f'{sd}: runs.csv differs from the rows its events and adjudications imply')
        rows += shard_rows
        by_shard[shard] = [b for b in d['block_order'] if any(r['family'] == b for r in mine)]
    if seen != set(d['shards']):
        fail(f'missing shards: {sorted(set(d["shards"]) - seen)}')
    if len(commits) != 1:
        fail(f'sessions ran different code commits: {sorted(commits)}')
    commit = commits.pop()
    if check_commit and hashlib.sha256(manifest_at(commit, repo)).hexdigest() != freeze_sha:
        fail('the sessions\' commit does not hold this freeze manifest')
    expected = {'model_id': fz['model']['id'], 'model_revision': fz['model']['revision'],
                'environment_id': fz['environment_id'], 'harness_commit': commit,
                'oracle_commit': commit}
    for col, val in expected.items():
        vals = {r[col] for r in rows}
        if vals != {val}:
            fail(f'{col}: expected {val!r}, got {sorted(vals)}')

    order = {r['run_id']: r['order'] for r in full}
    rows.sort(key=lambda r: order[r['run_id']])
    blocks = {}
    for fam in d['block_order']:
        b = [r for r in rows if r['family'] == fam]
        cut = [r for r in b if r['run_id'] in closed]
        never = [r for r in cut if r['run_id'] not in started]
        state = ('complete' if not cut else
                 'not_started' if len(never) == len(b) else 'partial')
        blocks[fam] = {'family': fam, 'templates': sorted({r['template_id'] for r in b}),
                       'scheduled': len(b), 'closed_out': len(cut), 'state': state,
                       'status_counts': {s: sum(1 for r in b if r['status'] == s)
                                         for s in sorted({r['status'] for r in b})}}
    states = [blocks[f]['state'] for f in d['block_order']]
    first_cut = next((i for i, s in enumerate(states) if s != 'complete'), len(states))
    complete = [b for b in blocks.values() if b['state'] == 'complete']
    report = {
        'freeze_sha256': freeze_sha, 'code_commit': commit, 'K_scheduled': d['K'],
        'K_in_complete_blocks': 3 * len(complete),
        'blocks': [blocks[f] for f in d['block_order']],
        'by_shard': {s: [{'family': f, 'state': blocks[f]['state']} for f in fams]
                     for s, fams in sorted(by_shard.items())},
        # with parallel shards a cut need not be a suffix of the published order (D8)
        'cut_is_global_suffix': all(s != 'complete' for s in states[first_cut:]),
        'closed_out_runs': len(closed),
        'exploratory_required': len(complete) < len(blocks),
        'analysis_flag': '--exploratory' if len(complete) < len(blocks) else '',
        'note': 'K evaluable per contrast is reported by twinguard_analysis.py'}
    return rows, report


def write(rows, report, out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    with open(out / 'runs.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, '') for k in COLUMNS})
    (out / 'truncation_report.json').write_text(json.dumps(report, indent=1))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--freeze', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('shards', nargs='+')
    a = ap.parse_args(argv)
    rows, report = merge(a.freeze, a.shards)
    write(rows, report, a.out)
    print(json.dumps({k: report[k] for k in ('K_scheduled', 'K_in_complete_blocks',
                                             'closed_out_runs', 'analysis_flag')}))


if __name__ == '__main__':
    main()
