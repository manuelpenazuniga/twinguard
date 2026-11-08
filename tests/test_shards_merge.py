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


FZ_MODEL = {'id': 'm', 'revision': 'v'}


def write_shard(d, runs, shard, freeze_sha, closed=(), env='env', extra_rows=(), started=(),
                commit='c', mutate=None):
    d.mkdir(parents=True)
    (d / 'manifest.json').write_text(json.dumps({'shard': shard,
                                                 'schedule_sha256': R.schedule_digest(runs)}))
    (d / 'sessions.jsonl').write_text(json.dumps({'session': 1, 'shard': shard, 'code_commit': commit,
                                                  'freeze_sha256': freeze_sha}) + '\n')
    rows, events = [], []
    for r in list(runs) + list(extra_rows):
        cut = r['run_id'] in closed
        row = {k: r.get(k, '') for k in R.COLUMNS}
        row.update(status='infra_failed' if cut else 'patch', model_id='m', model_revision='v',
                   harness_commit=commit, oracle_commit=commit, environment_id=env)
        if mutate:
            mutate(row)
        rows.append(row)
        if not cut or r['run_id'] in started:
            events.append({'run_id': r['run_id'], 'event': 'start'})
        events.append({'run_id': r['run_id'], 'final': True, 'closed_out': cut, 'row': row})
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
          'seeds': {'order_seed': 20261107}, 'model': FZ_MODEL, 'environment_id': 'env'}
    p = tmp_path / 'manifest.json'
    p.write_text(json.dumps(fz))
    return p, hashlib.sha256(p.read_bytes()).hexdigest()


def merge(fz, dirs):
    return M.merge(fz, dirs, check_commit=False)


def test_merge_complete_and_truncated(tmp_path):
    runs = full()
    fz, sha = freeze(tmp_path, runs)
    s1, s2 = R.shard_runs(runs, (1, 2)), R.shard_runs(runs, (2, 2))
    write_shard(tmp_path / 'a', s1, '1/2', sha)
    write_shard(tmp_path / 'b', s2, '2/2', sha)
    rows, rep = merge(fz, [tmp_path / 'a', tmp_path / 'b'])
    assert len(rows) == len(runs) and not rep['exploratory_required']
    assert rep['K_in_complete_blocks'] == 30 and rep['cut_is_global_suffix']

    # time cut: the last block of shard 2 never started, the one before is partial
    last, prev = blocks_of(s2)[-1], blocks_of(s2)[-2]
    closed = {r['run_id'] for r in s2 if r['family'] == last}
    closed |= set([r['run_id'] for r in s2 if r['family'] == prev][:5])
    write_shard(tmp_path / 'c', s2, '2/2', sha, closed=closed)
    rows, rep = merge(fz, [tmp_path / 'a', tmp_path / 'c'])
    states = {b['family']: b['state'] for b in rep['blocks']}
    assert states[last] == 'not_started' and states[prev] == 'partial'
    assert rep['exploratory_required'] and rep['analysis_flag'] == '--exploratory'
    assert rep['K_in_complete_blocks'] == 24
    assert not rep['cut_is_global_suffix']     # shard 1 finished later blocks: declared (D8)
    assert [b['state'] for b in rep['by_shard']['2/2']][-2:] == ['partial', 'not_started']

    # a closed-out block where one run had started is partial, not "not started"
    one = [r['run_id'] for r in s2 if r['family'] == last][:1]
    write_shard(tmp_path / 'd', s2, '2/2', sha, closed=closed, started=one)
    _, rep = merge(fz, [tmp_path / 'a', tmp_path / 'd'])
    assert {b['family']: b['state'] for b in rep['blocks']}[last] == 'partial'

    from runner import analyze
    cmd = analyze.analysis_cmd('x.csv', rep, 4, 'o.json')
    assert '--exploratory' in cmd
    assert '--exploratory' not in analyze.analysis_cmd('x.csv', {'exploratory_required': False}, 4, 'o')


def test_merge_refuses_inconsistent_shards(tmp_path):
    runs = full()
    fz, sha = freeze(tmp_path, runs)
    s1, s2 = R.shard_runs(runs, (1, 2)), R.shard_runs(runs, (2, 2))
    write_shard(tmp_path / 'a', s1, '1/2', sha)
    cases = {
        'env': dict(env='other'),                                     # not the frozen env
        'commit': dict(commit='zzz'),                                 # other code commit
        'freeze': dict(freeze_sha256='f' * 64),
        'dup': dict(extra_rows=s1[:1]),                               # run of the other shard
        'seed': dict(mutate=lambda row: row.update(seed='1')),        # seeds not frozen
        'frame': dict(mutate=lambda row: row.update(framing='N')),
    }
    for name, kw in cases.items():
        fsha = kw.pop('freeze_sha256', sha)
        write_shard(tmp_path / name, s2, '2/2', fsha, **kw)
        with pytest.raises(SystemExit):
            merge(fz, [tmp_path / 'a', tmp_path / name])
    with pytest.raises(SystemExit):                                   # missing shard
        merge(fz, [tmp_path / 'a'])
    write_shard(tmp_path / 'bad', s2, '2/2', sha)
    with open(tmp_path / 'bad' / 'attempts.jsonl', 'a') as f:
        f.write('{broken\n')
    with pytest.raises(SystemExit):                                   # unreadable event
        merge(fz, [tmp_path / 'a', tmp_path / 'bad'])
    write_shard(tmp_path / 'nos', s2, '2/2', sha)
    (tmp_path / 'nos' / 'sessions.jsonl').write_text('')
    with pytest.raises(SystemExit):                                   # empty session log
        merge(fz, [tmp_path / 'a', tmp_path / 'nos'])


def test_server_down_stops_the_session(tmp_path):
    import argparse
    from harness.loop import EndpointError
    b = tmp_path / 'bank'
    import shutil
    shutil.copytree(ROOT / 'tests' / 'fixtures' / 'tpl_m1', b / 'FIXTURE.m1_toy')
    m = json.loads((b / 'FIXTURE.m1_toy' / 'template.json').read_text())
    m['issue_paraphrases'] = [m['problem_statement']] * 4
    (b / 'FIXTURE.m1_toy' / 'template.json').write_text(json.dumps(m))
    spec = tmp_path / 'spec.csv'
    spec.write_text('template_id,split,family,mechanism\nFIXTURE.m1_toy,pilot,logistics,M1\n')

    class Dead:
        model = 'fake'

        def chat(self, body):
            raise EndpointError('connection refused', None, False)

        def models(self):
            raise OSError('connection refused')
    a = argparse.Namespace(split='pilot', replicates=1, order_seed=1, bank=str(b), spec=str(spec),
                           out=str(tmp_path / 'out'), work=str(tmp_path / 'work'), base_url=None,
                           model='fake', concurrency=1, budget_json='{"tool_calls": 5}',
                           run_as=None, eval_user=None, model_revision='v',
                           allow_unisolated=True, environment_id='e', code_commit='c', limit=0,
                           keep_work=False, stop_at=0)
    runs = R.schedule(b, spec, 'pilot', 1, 1)[:3]
    r = R.Runner(a, client=Dead())
    with pytest.raises(R.ServerDown):
        r.run(runs)
    assert not r.done()                     # no run was recorded as a result
    assert r.tries_started(runs[0]['run_id']) == 1
