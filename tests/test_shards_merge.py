"""Parallel confirmatory shards and their merge with the truncation report (7.4, Annex A)."""
import csv
import hashlib
import json
import subprocess
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


EV = {'M': 1, 'oracle': {'W': 0, 'crash': 0}, 'tests': {'passed': 1}}
EMPTY_SHA = hashlib.sha256(b'').hexdigest()


def write_shard(d, runs, shard, freeze_sha, closed=(), env='env', extra_rows=(), started=(),
                commit='c', mutate=None, sessions=None, ev_of=None):
    """A shard as the runner leaves it: events (with evaluations), the CSV they imply."""
    d.mkdir(parents=True)
    (d / 'manifest.json').write_text(json.dumps({'shard': shard,
                                                 'schedule_sha256': R.schedule_digest(runs)}))
    sessions = sessions or [{'session': 1, 'parent_sha256': None}]
    (d / 'sessions.jsonl').write_text(''.join(
        json.dumps({'shard': shard, 'code_commit': commit, 'freeze_sha256': freeze_sha, **s}) + '\n'
        for s in sessions))
    rows, events = [], []
    for r in list(runs) + list(extra_rows):
        cut = r['run_id'] in closed
        row = {k: r.get(k) for k in R.COLUMNS}
        row.update(model_id='m', model_revision='v', harness_commit=commit, oracle_commit=commit,
                   environment_id=env)
        if cut:
            row.update(status='infra_failed', W=None, F=None, M=None, crash=None,
                       termination='closed_out')
        else:
            ev = ev_of(r) if ev_of else EV
            row.update(zip(M.OUTCOME, R.outcome({}, ev)), termination='submit')
        if mutate:
            mutate(row)
        rows.append({k: ('' if v is None else v) for k, v in row.items()})
        if not cut or r['run_id'] in started:
            events.append({'run_id': r['run_id'], 'event': 'start'})
        events.append({'run_id': r['run_id'], 'final': True, 'closed_out': cut, 'row': row,
                       'summary': {}, 'needs_adjudication': False,
                       'patch_sha256': EMPTY_SHA,
                       'evaluation': None if cut else (ev_of(r) if ev_of else EV)})
    with open(d / 'runs.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=R.COLUMNS)
        w.writeheader()
        w.writerows(rows)
    (d / 'attempts.jsonl').write_text(''.join(json.dumps(e) + '\n' for e in events))


def edit_csv(d, fn):
    rows = list(csv.DictReader(open(d / 'runs.csv')))
    fn(rows)
    with open(d / 'runs.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=R.COLUMNS)
        w.writeheader()
        w.writerows(rows)


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


def test_merge_refuses_contradictory_records(tmp_path):
    """Astra day 3c: the CSV must be what the events and adjudications imply."""
    runs = full()
    fz, sha = freeze(tmp_path, runs)
    s1, s2 = R.shard_runs(runs, (1, 2)), R.shard_runs(runs, (2, 2))
    write_shard(tmp_path / 'a', s1, '1/2', sha)
    last = [r['run_id'] for r in s2 if r['family'] == blocks_of(s2)[-1]]

    def case(name, **kw):
        write_shard(tmp_path / name, s2, '2/2', sha, **kw)
        return tmp_path / name

    d = case('w_csv')                                    # W changed in the CSV only
    edit_csv(d, lambda rows: rows[0].update(W='1'))
    d2 = case('w_event', mutate=lambda row: row.update(W=1) if row['run_id'] == s2[0]['run_id'] else None)
    d3 = case('cut_csv')                                 # closed-out rows without the event mark
    edit_csv(d3, lambda rows: [r.update(status='infra_failed', W='', F='', M='', crash='',
                                        termination='closed_out')
                               for r in rows if r['run_id'] in last])
    d4 = case('cut_event', closed=set(last))
    ev = [json.loads(x) for x in (d4 / 'attempts.jsonl').read_text().splitlines()]
    for e in ev:
        e.pop('closed_out', None)
    (d4 / 'attempts.jsonl').write_text(''.join(json.dumps(e) + '\n' for e in ev))
    d5 = case('orphan', sessions=[{'session': 1, 'parent_sha256': None},
                                  {'session': 2, 'parent_sha256': None}])
    d6 = case('adj')
    (d6 / 'adjudications.jsonl').write_text(json.dumps({'run_id': 'nope', 'resolved': True}) + '\n')
    for bad in (d, d2, d3, d4, d5, d6):
        with pytest.raises(SystemExit):
            merge(fz, [tmp_path / 'a', bad])
    ok = case('chain', sessions=[{'session': 1, 'parent_sha256': None},
                                 {'session': 2, 'parent_sha256': 'a' * 64}])
    rows, rep = merge(fz, [tmp_path / 'a', ok])
    assert len(rows) == len(runs)


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
                           model='fake', concurrency=2, budget_json='{"tool_calls": 5}',
                           run_as=None, eval_user=None, model_revision='v',
                           allow_unisolated=True, environment_id='e', code_commit='c', limit=0,
                           keep_work=False, stop_at=0)
    runs = R.schedule(b, spec, 'pilot', 1, 1)[:8]
    r = R.Runner(a, client=Dead())
    with pytest.raises(R.ServerDown):
        r.run(runs)
    assert not r.done()                     # no run was recorded as a result
    started = [x for x in runs if r.tries_started(x['run_id'])]
    assert 1 <= len(started) <= 2           # only the runs in flight spent a try
    assert all(r.tries_started(x['run_id']) == 1 for x in started)


def test_analyze_runs_only_verified_frozen_code(tmp_path):
    """Astra day 3c: the analysis runs from a git archive of the frozen commit, every frozen
    file checked against the manifest hashes; a modified file is refused."""
    from runner import analyze as A
    head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True,
                          text=True, check=True).stdout.strip()
    dest = tmp_path / 'x'
    dest.mkdir()
    A.extract(head, ROOT, dest)
    files = {p: hashlib.sha256((dest / p).read_bytes()).hexdigest()
             for p in ('runner/merge.py', 'twinguard/twinguard_analysis.py')}
    man = {'files': {'g': files}, 'templates': {}}
    (dest / 'freeze').mkdir(exist_ok=True)
    (dest / 'freeze' / 'manifest.json').write_text(json.dumps(man))
    sha = hashlib.sha256((dest / 'freeze' / 'manifest.json').read_bytes()).hexdigest()
    assert A.verify_extraction(dest, man, sha) == 2
    with pytest.raises(SystemExit):
        A.verify_extraction(dest, man, 'f' * 64)                  # not this freeze
    with open(dest / 'twinguard' / 'twinguard_analysis.py', 'a') as f:
        f.write('# changed\n')
    with pytest.raises(SystemExit):
        A.verify_extraction(dest, man, sha)


def test_analyze_end_to_end_from_frozen_commit(tmp_path):
    """Extraction -> verification -> re-execution -> merge -> frozen analysis (Astra day 3d)."""
    repo = tmp_path / 'repo'
    subprocess.run(['git', 'clone', '-q', '--no-hardlinks', str(ROOT), str(repo)], check=True)
    git = lambda *a: subprocess.run(['git', *a], cwd=repo, check=True, capture_output=True,
                                    text=True).stdout.strip()
    import shutil
    for rel in ('runner/analyze.py', 'runner/merge.py', 'runner/runner.py', 'runner/secondary.py',
                'resource/cli.py', 'resource/tables.py'):
        (repo / rel).parent.mkdir(exist_ok=True)
        shutil.copyfile(ROOT / rel, repo / rel)      # the working-tree code under test
    runs = full()
    shards = {f'{i}/2': {'schedule_sha256': R.schedule_digest(R.shard_runs(runs, (i, 2)))}
              for i in (1, 2)}
    files = {p: hashlib.sha256((repo / p).read_bytes()).hexdigest()
             for p in ('runner/merge.py', 'runner/analyze.py', 'twinguard/twinguard_analysis.py')}
    fam = blocks_of(runs)[0]
    fz = {'design': {'S': 1, 'K': 30, 'schedule_sha256': R.schedule_digest(runs),
                     'block_order': blocks_of(runs), 'shards': shards,
                     'sensitivity': {'exclude_families': [fam], 'K': 27,
                                     'templates_dropped': sorted({r['template_id'] for r in runs
                                                                  if r['family'] == fam})}},
          'seeds': {'order_seed': 20261107}, 'environment_id': 'env',
          'model': {'id': R.MODEL_ID, 'revision': 'v'},
          'files': {'g': files}, 'templates': {}}
    (repo / 'freeze').mkdir(exist_ok=True)
    (repo / 'freeze' / 'manifest.json').write_text(json.dumps(fz))
    git('add', 'freeze/manifest.json', 'runner', 'resource')
    git('-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-q', '-m', 'freeze')
    commit = git('rev-parse', 'HEAD')
    sha = hashlib.sha256((repo / 'freeze' / 'manifest.json').read_bytes()).hexdigest()
    s1, s2 = R.shard_runs(runs, (1, 2)), R.shard_runs(runs, (2, 2))
    last = {r['run_id'] for r in s2 if r['family'] == blocks_of(s2)[-1]}
    real = lambda row: row.update(model_id=R.MODEL_ID)
    def ev_of(r):              # variable outcomes (Astra): W depends on the run, A higher
        u = int(hashlib.sha256(r['run_id'].encode()).hexdigest()[:8], 16) / 16 ** 8
        return {**EV, 'oracle': {'W': int(u < (0.45 if r['framing'] == 'A' else 0.3)), 'crash': 0}}
    write_shard(tmp_path / 'a', s1, '1/2', sha, commit=commit, mutate=real, ev_of=ev_of)
    write_shard(tmp_path / 'b', s2, '2/2', sha, commit=commit, closed=last, mutate=real, ev_of=ev_of)
    out = tmp_path / 'out'
    r = subprocess.run([sys.executable, str(repo / 'runner' / 'analyze.py'), '--freeze',
                        str(repo / 'freeze' / 'manifest.json'), '--out', str(out),
                        str(tmp_path / 'a'), str(tmp_path / 'b')],
                       capture_output=True, text=True, cwd=str(tmp_path))
    assert (out / "analysis_hashes.json").exists(), r.stdout[-1500:] + r.stderr[-3000:]
    hashes = json.loads((out / "analysis_hashes.json").read_text())
    assert hashes['frozen_commit'] == commit and '--exploratory' in hashes['cmd']
    assert 'twinguard_frozen_' in hashes['cmd'][0]           # the extraction, not the checkout
    assert json.loads((out / 'truncation_report.json').read_text())['exploratory_required']
    assert (out / 'analysis_output.txt').exists()
    res = json.loads((out / 'analysis_output.json').read_text())
    assert res['analysis_status'] != 'CONFIRMATORY'                  # truncated: exploratory
    assert 'no gsc column' not in json.dumps(res['EXPLORATORY_gsc_decomposition'])
    assert hashes['gate_rc'] == 0 and (out / 'gate_output.json').exists()
    assert not (out / 'secondary_hashes.json').exists()              # one hash file: analyze's
    sens = json.loads((out / 'analysis_sensitivity.json').read_text())
    assert hashes['sensitivity']['rc'] == 0 and hashes['sensitivity']['templates'] == 27
    assert sens['analysis_status'] == 'EXPLORATORY' and sens['n_templates'] == 27
    assert fam not in json.dumps(sens['EXPLORATORY_heterogeneity_and_stability']['leave_one_family_out'])
    assert not sens['H1_PRIMARY_W_A_minus_N']['HC3_95']['zero_variance']      # not degenerate
    lofo = res['EXPLORATORY_heterogeneity_and_stability']['leave_one_family_out'][fam]
    assert abs(lofo['estimate'] - sens['H1_PRIMARY_W_A_minus_N']['HC3_95']['estimate']) < 1e-9
    t = subprocess.run([sys.executable, str(repo / 'resource' / 'tables.py'), '--results', str(out),
                        '--freeze', str(repo / 'freeze' / 'manifest.json'),
                        '--out', str(tmp_path / 't.md')], capture_output=True, text=True)
    assert t.returncode == 0, t.stderr[-1500:]
    assert 'equals the sensitivity H1: yes' in (tmp_path / 't.md').read_text()
    # resource contract (17): the published labels and tables reproduce from the results dir
    fzp = str(repo / 'freeze' / 'manifest.json')
    rep = subprocess.run([sys.executable, str(repo / 'resource' / 'cli.py'), 'reproduce',
                          '--results', str(out), '--freeze', fzp], capture_output=True, text=True)
    report = json.loads(rep.stdout)
    assert report['code']['freeze_held_by_commit'] is True and not report['code']['mismatch']
    so = report['sensitivity_output']
    assert so['reproduced'] and so['input_rederived_identical'] and so['cmd_matches_freeze']
    assert report['analysis_cmd_matches_freeze']
    assert report['gate_output']['identical']
    assert report['hashes']['mismatch'] == [] and report['schema'] == 'ok'
    assert report['analysis_rc']['published'] == report['analysis_rc']['reproduced']
    assert report['analysis_output']['identical'] and report['reproduced'], report
    (out / 'runs.csv').write_text((out / 'runs.csv').read_text().replace(',patch,', ',no_patch,', 1))
    rep = subprocess.run([sys.executable, str(repo / 'resource' / 'cli.py'), 'reproduce',
                          '--results', str(out), '--freeze', fzp], capture_output=True, text=True)
    assert rep.returncode != 0                                # a changed label is caught
    r2 = subprocess.run([sys.executable, str(repo / 'runner' / 'analyze.py'), '--freeze',
                         str(repo / 'freeze' / 'manifest.json'), '--out', str(out),
                         str(tmp_path / 'a'), str(tmp_path / 'b')], capture_output=True, text=True)
    assert r2.returncode != 0 and 'refusing to rerun' in r2.stderr


def test_analyze_secondary_failure_never_blocks_primary(tmp_path):
    """Prespecified (D10): a patch that does not match the evaluated patch makes the
    secondary analyses fail; the single analysis still runs, on runs.csv, and the failure is
    recorded."""
    repo = tmp_path / 'repo'
    subprocess.run(['git', 'clone', '-q', '--no-hardlinks', str(ROOT), str(repo)], check=True)
    import shutil
    for rel in ('runner/analyze.py', 'runner/merge.py', 'runner/runner.py', 'runner/secondary.py'):
        shutil.copyfile(ROOT / rel, repo / rel)
    git = lambda *a: subprocess.run(['git', *a], cwd=repo, check=True, capture_output=True,
                                    text=True).stdout.strip()
    runs = full()
    shards = {f'{i}/2': {'schedule_sha256': R.schedule_digest(R.shard_runs(runs, (i, 2)))}
              for i in (1, 2)}
    fz = {'design': {'S': 1, 'K': 30, 'schedule_sha256': R.schedule_digest(runs),
                     'block_order': blocks_of(runs), 'shards': shards},
          'seeds': {'order_seed': 20261107}, 'environment_id': 'env',
          'model': {'id': R.MODEL_ID, 'revision': 'v'},
          'files': {'g': {p: hashlib.sha256((repo / p).read_bytes()).hexdigest()
                          for p in ('runner/analyze.py', 'runner/secondary.py')}},
          'templates': {}}
    (repo / 'freeze').mkdir(exist_ok=True)
    (repo / 'freeze' / 'manifest.json').write_text(json.dumps(fz))
    git('add', 'freeze/manifest.json', 'runner')
    git('-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-q', '-m', 'freeze')
    commit = git('rev-parse', 'HEAD')
    sha = hashlib.sha256((repo / 'freeze' / 'manifest.json').read_bytes()).hexdigest()
    real = lambda row: row.update(model_id=R.MODEL_ID)
    s1, s2 = R.shard_runs(runs, (1, 2)), R.shard_runs(runs, (2, 2))
    write_shard(tmp_path / 'a', s1, '1/2', sha, commit=commit, mutate=real)
    write_shard(tmp_path / 'b', s2, '2/2', sha, commit=commit, mutate=real)
    (tmp_path / 'a' / 'patches').mkdir()
    (tmp_path / 'a' / 'patches' / (s1[0]['run_id'].replace(':', '__') + '.patch')).write_text('x')
    out = tmp_path / 'out'
    r = subprocess.run([sys.executable, str(repo / 'runner' / 'analyze.py'), '--freeze',
                        str(repo / 'freeze' / 'manifest.json'), '--out', str(out),
                        str(tmp_path / 'a'), str(tmp_path / 'b')], capture_output=True, text=True)
    h = json.loads((out / 'analysis_hashes.json').read_text())
    assert 'differs from the evaluated patch' in h['secondary_error'], r.stderr[-1500:]
    assert h['cmd'][1].endswith('runs.csv') and h['rc'] == 0
    assert (out / 'analysis_started.json').exists()
    assert json.loads((out / 'analysis_output.json').read_text())['analysis_status'] == 'CONFIRMATORY'


def test_sensitivity_input_must_match_the_freeze(tmp_path):
    """Opus review: K and the dropped templates are checked against the freeze, inside the
    guard; a mismatch is recorded, nothing is run."""
    from runner import analyze
    runs = full()
    rows = [{k: r.get(k, '') for k in R.COLUMNS} for r in runs]
    with open(tmp_path / 'in.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=R.COLUMNS)
        w.writeheader()
        w.writerows(rows)
    fam = runs[0]['family']
    dropped = sorted({r['template_id'] for r in runs if r['family'] == fam})
    bad = analyze.run_sensitivity({'exclude_families': [fam], 'K': 30, 'templates_dropped': dropped},
                                  tmp_path / 'in.csv', 1, tmp_path)
    assert 'error' in bad and 'does not match the freeze' in bad['error']
    bad2 = analyze.run_sensitivity({'exclude_families': ['nope'], 'K': 27,
                                    'templates_dropped': dropped}, tmp_path / 'in.csv', 1, tmp_path)
    assert 'error' in bad2 and not (tmp_path / 'analysis_sensitivity.json').exists()
