"""Parallel confirmatory shards and their merge with the truncation report (7.4, Annex A)."""
import csv
import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from runner import merge as M  # noqa: E402
from runner import runner as R  # noqa: E402

BANK, SPEC = ROOT / 'bank' / 'templates', ROOT / 'bank' / 'spec_matrix.csv'


def full(S=1):
    return R.schedule(BANK, SPEC, 'confirmatory', S, 20261107)


def blocks_of(runs):
    out = []
    for r in runs:
        if not out or out[-1] != r['family']:
            out.append(r['family'])
    return out


def test_shards_partition_alternate_blocks():
    runs = full()
    order = blocks_of(runs)
    s1, s2 = R.shard_runs(runs, (1, 2)), R.shard_runs(runs, (2, 2))
    assert blocks_of(s1) == order[0::2] and blocks_of(s2) == order[1::2]
    assert sorted(r['run_id'] for r in s1 + s2) == sorted(r['run_id'] for r in runs)
    assert [r['order'] for r in s1] == sorted(r['order'] for r in s1)   # global order kept
    with pytest.raises(ValueError):
        R.parse_shard('3/2')


def test_results_without_manifest_are_refused(tmp_path):
    import argparse
    out = tmp_path / 'out'
    out.mkdir()
    (out / 'attempts.jsonl').write_text('{"run_id": "x", "final": true}\n')
    a = argparse.Namespace(split='confirmatory', replicates=1, order_seed=1, bank=str(BANK),
                           spec=str(SPEC), out=str(out), model='m', model_revision='r',
                           concurrency=1, environment_id='e', code_commit='c',
                           budget_json='', shard='1/2', close_out=True, run_as=None,
                           eval_user=None, work=str(tmp_path / 'w'), keep_work=False, stop_at=0)
    r = R.Runner(a, client=object())
    with pytest.raises(R.ConfigError):
        r.check_manifest(R.shard_runs(full(), (1, 2)), offline=True)


def write_shard(d, runs, shard, freeze_sha, closed=(), env='env', extra_rows=()):
    d.mkdir(parents=True)
    (d / 'manifest.json').write_text(json.dumps({'shard': shard,
                                                 'schedule_sha256': R.schedule_digest(runs)}))
    (d / 'sessions.jsonl').write_text(json.dumps({'session': 1, 'shard': shard,
                                                  'freeze_sha256': freeze_sha}) + '\n')
    rows, events = [], []
    for r in list(runs) + list(extra_rows):
        cut = r['run_id'] in closed
        row = {k: r.get(k, '') for k in R.COLUMNS}
        row.update(status='infra_failed' if cut else 'patch', model_id='m', model_revision='v',
                   harness_commit='c', oracle_commit='c', environment_id=env)
        rows.append(row)
        events.append({'run_id': r['run_id'], 'final': True, 'closed_out': cut})
    with open(d / 'runs.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=R.COLUMNS)
        w.writeheader()
        w.writerows(rows)
    (d / 'attempts.jsonl').write_text(''.join(json.dumps(e) + '\n' for e in events))


def freeze(tmp_path, runs):
    shards = {f'{i}/2': {'schedule_sha256': R.schedule_digest(R.shard_runs(runs, (i, 2)))}
              for i in (1, 2)}
    fz = {'design': {'S': 1, 'K': 30, 'schedule_sha256': R.schedule_digest(runs),
                     'block_order': blocks_of(runs), 'shards': shards},
          'seeds': {'order_seed': 20261107}}
    p = tmp_path / 'manifest.json'
    p.write_text(json.dumps(fz))
    return p, hashlib.sha256(p.read_bytes()).hexdigest()


def test_merge_complete_and_truncated(tmp_path):
    runs = full()
    fz, sha = freeze(tmp_path, runs)
    s1, s2 = R.shard_runs(runs, (1, 2)), R.shard_runs(runs, (2, 2))
    write_shard(tmp_path / 'a', s1, '1/2', sha)
    write_shard(tmp_path / 'b', s2, '2/2', sha)
    rows, rep = M.merge(fz, [tmp_path / 'a', tmp_path / 'b'])
    assert len(rows) == len(runs) and not rep['exploratory_required']
    assert rep['K_in_complete_blocks'] == 30

    # time cut: the last block of shard 2 never started, the one before is partial
    last = blocks_of(s2)[-1]
    prev = blocks_of(s2)[-2]
    closed = {r['run_id'] for r in s2 if r['family'] == last}
    closed |= set([r['run_id'] for r in s2 if r['family'] == prev][:5])
    write_shard(tmp_path / 'c', s2, '2/2', sha, closed=closed)
    rows, rep = M.merge(fz, [tmp_path / 'a', tmp_path / 'c'])
    states = {b['family']: b['state'] for b in rep['blocks']}
    assert states[last] == 'not_started' and states[prev] == 'partial'
    assert rep['exploratory_required'] and rep['analysis_flag'] == '--exploratory'
    assert rep['K_in_complete_blocks'] == 24


def test_merge_refuses_inconsistent_shards(tmp_path):
    runs = full()
    fz, sha = freeze(tmp_path, runs)
    s1, s2 = R.shard_runs(runs, (1, 2)), R.shard_runs(runs, (2, 2))
    write_shard(tmp_path / 'a', s1, '1/2', sha)
    write_shard(tmp_path / 'b', s2, '2/2', sha, env='other')          # mixed environments
    with pytest.raises(SystemExit):
        M.merge(fz, [tmp_path / 'a', tmp_path / 'b'])
    with pytest.raises(SystemExit):                                   # missing shard
        M.merge(fz, [tmp_path / 'a'])
    write_shard(tmp_path / 'c', s2, '2/2', 'f' * 64)                  # other freeze
    with pytest.raises(SystemExit):
        M.merge(fz, [tmp_path / 'a', tmp_path / 'c'])
    write_shard(tmp_path / 'd', s2, '2/2', sha, extra_rows=s1[:1])     # duplicate run
    with pytest.raises(SystemExit):
        M.merge(fz, [tmp_path / 'a', tmp_path / 'd'])
