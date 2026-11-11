"""D17 (ladder): Gemma 4 26B-A4B, E2B and E4B under the D15 request on x3's Colab A100, with the x3
machinery: kernel mode, model switching, start-up failures, seal parameters, bootstrap downloads
and the single analysis (synthetic data)."""
import base64
import csv
import importlib.util
import io
import json
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))

from followup import analyze_e4b as E, analyze_ladder as L, analyze_x3 as AN, ladder_seal as LS  # noqa: E402
from runner import runner as R  # noqa: E402
from test_followup_x3 import synth, write, results_root as x3_root, M as X3M, SEAL as X3SEAL  # noqa: E402

SCRIPT = ROOT / 'notebooks' / 'pilot_l4' / 'pilot_l4.py'
MODEL = 'google/gemma-4-31b-it-qat-w4a16-ct'
LSEAL = 'l' * 64


def kernel(monkeypatch, tmp_path, **defs):
    s = importlib.util.spec_from_file_location('tg_kernel_ladder', SCRIPT)
    k = importlib.util.module_from_spec(s)
    s.loader.exec_module(k)
    monkeypatch.setattr(k, 'OUT', tmp_path / 'r.json')
    monkeypatch.setattr(k, 'RESULTS_DIR', tmp_path / 'tgv' / 'results')
    for n, v in defs.items():
        monkeypatch.setattr(k, n, v)
    return k


def load_kernel():
    s = importlib.util.spec_from_file_location('tg_kernel_ladder0', SCRIPT)
    k = importlib.util.module_from_spec(s)
    s.loader.exec_module(k)
    return k


def test_seal_blocks_agree_with_kernel_and_bootstrap():
    k = load_kernel()
    assert [b['name'] for b in LS.BLOCKS] == ['ladder_e4b_main', 'ladder_e2b', 'ladder_26b']
    assert [b['model'] for b in LS.BLOCKS] == list(load_kernel().LADDER_KINDS)
    assert all(b['start_by_epoch'] is None and b['framings'] == ['N'] and b['runs'] == 120
               for b in LS.BLOCKS)
    assert len(AN.scheduled('spec_main.csv', ('N',))) == 120
    for b in LS.BLOCKS:
        spec = k.MODEL_SPECS[b['model']]
        assert b['model'] in k.LADDER_KINDS
        assert spec['revision'] == b['revision'] and spec['hf_repo'] == b['hf_repo']
        assert b['environment_id'] == 'colab-A100|py3.12|vllm0.19.1|tp1|' + spec['tag']
    assert k.MODEL_SPECS['e4b_hf']['revision'] == E.REVISION      # the same E4B as D16
    assert k.MODEL_SPECS['e4b_hf']['hf'] is k.HF_EXPECTED_E4B_HF
    # the 26B-A4B uses the 31B's chat template, E2B the E4B's (no overlay is needed); both
    # weight shards of the 26B-A4B and its index are hash-checked
    assert k.HF_EXPECTED_26B['chat_template.jinja'] == k.HF_EXPECTED['chat_template.jinja']
    assert {'model-00001-of-00002.safetensors', 'model-00002-of-00002.safetensors',
            'model.safetensors.index.json'} <= set(k.HF_EXPECTED_26B)
    assert k.HF_EXPECTED_E2B['chat_template.jinja'] == k.HF_EXPECTED_E4B['chat_template.jinja']
    boot = (ROOT / 'notebooks' / 'colab' / 'colab_bootstrap.py').read_text()
    ns = {}
    exec(boot[boot.index('LADDER_HF = '):boot.index('\n\n', boot.index('LADDER_HF = '))], ns)
    assert {(r, v, d) for r, v, d in ns['LADDER_HF']} == \
        {(k.MODEL_SPECS[x]['hf_repo'], k.MODEL_SPECS[x]['revision'], k.MODEL_SPECS[x]['hf_dir'])
         for x in k.LADDER_KINDS}
    assert LS.STOP_AT_EPOCH == 1794409200 and {'followup/ladder_manifest.json'} <= LS.OWN
    assert 'followup/analyze_ladder.py' in LS.ANALYSIS_PATHS and L.MANIFEST == ROOT / 'followup' / 'ladder_manifest.json'
    assert 'ladder' in k.FOLLOWUP_MODES and k.FOLLOWUP_MANIFEST['ladder'] == 'followup/ladder_manifest.json'


def test_ladder_is_colab_80gb_only(monkeypatch, tmp_path):
    k = kernel(monkeypatch, tmp_path, MODE='ladder', PLATFORM='kaggle')
    monkeypatch.setattr(k, 'sh', lambda c: 'NVIDIA L4, 23034 MiB, 550\n' * 4)
    with pytest.raises(SystemExit, match='Colab only'):
        k.gpu_guard()
    k = kernel(monkeypatch, tmp_path, MODE='ladder', PLATFORM='colab')
    monkeypatch.setattr(k, 'sh', lambda c: 'NVIDIA A100-SXM4-40GB, 40960 MiB, 550\n')
    with pytest.raises(SystemExit, match='80 GB'):
        k.gpu_guard()
    monkeypatch.setattr(k, 'sh', lambda c: 'NVIDIA A100-SXM4-80GB, 81920 MiB, 550\n')
    k.gpu_guard()
    monkeypatch.setattr(k, 'sh', lambda c: '81920')
    assert k.colab_gpu_util() == 0.9
    with pytest.raises(RuntimeError, match='no model selected'):
        k.model_spec()
    monkeypatch.setattr(k, 'LADDER_KIND', 'e2b')
    assert k.model_spec()['revision'].startswith('971342c')
    assert k.environment_id() == 'colab-A100|py3.12|vllm0.19.1|tp1|model:e2b-971342c'
    assert k.environment_id('26b_a4b').endswith('model:26b-a4b-4d7ae49')
    assert str(k.RESULTS_DIR).endswith('results')


def test_ladder_model_path_serves_hf_files_without_overlay(monkeypatch, tmp_path):
    k = kernel(monkeypatch, tmp_path, MODE='ladder', LADDER_KIND='26b_a4b')
    src = tmp_path / 'hf' / 'gemma-4-26b-a4b@4d7ae49'
    src.mkdir(parents=True)
    for n in ('model.safetensors', 'chat_template.jinja', 'config.json'):
        (src / n).write_text('hf ' + n)
    real = k.Path

    def fake_path(p, *a):
        return real(str(p).replace('/kaggle/input/hf', str(tmp_path / 'hf')), *a)
    monkeypatch.setattr(k, 'Path', fake_path)
    monkeypatch.setitem(k.MODEL_SPECS['26b_a4b'], 'dest', str(tmp_path / 'dest'))
    out = k.model_path()
    assert (out / 'chat_template.jinja').is_symlink()
    assert (out / 'chat_template.jinja').read_text() == 'hf chat_template.jinja'


def ladder_kernel(monkeypatch, tmp_path):
    k = kernel(monkeypatch, tmp_path, MODE='ladder', PLATFORM='colab')
    k.X3.update({'blocks': [dict(b) for b in LS.BLOCKS], 'stop_at_epoch': 4e9,
                 'environment_id': 'x'})
    monkeypatch.setattr(k, 'KERNEL_T0', 2e9)
    monkeypatch.setattr(k, 'stop', lambda procs: None)
    return k


def fake_rows(k, name, n=120):
    d = k.RESULTS_DIR / name
    d.mkdir(parents=True, exist_ok=True)
    with open(d / 'runs.csv', 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['run_id'])
        w.writerows([[f'{name}:{i}'] for i in range(n)])


def test_ladder_block_startup_failure_moves_on(monkeypatch, tmp_path):
    k = ladder_kernel(monkeypatch, tmp_path)
    served, ran = [], []

    def serve(kind, procs):
        served.append(kind)
        if kind == 'e2b':
            raise RuntimeError('engine failed: unsupported architecture')
        return {'ok': True}

    def run(code, mode, name, extra):
        assert mode == 'x3' and '--framings' in extra and 'N' in extra
        ran.append(name)
        fake_rows(k, name)
        return {'rc': 0}
    monkeypatch.setattr(k, 'ladder_serve', serve)
    monkeypatch.setattr(k, 'run_block', run)
    monkeypatch.setattr(k, 'code_dir', lambda: ROOT)
    res = k.ladder_block(ROOT, [])
    assert served == ['e4b_hf', 'e2b', '26b_a4b'] and ran == ['ladder_e4b_main', 'ladder_26b']
    f = json.loads((k.RESULTS_DIR / 'ladder_e2b' / 'startup_failed.json').read_text())
    assert f['model'] == 'e2b' and 'unsupported architecture' in f['error']
    assert res['ladder_e2b']['startup_failed'] and k.ladder_status({'ok': True}) == 'complete'
    # a resumed session skips what is done or failed, and serves nothing
    served.clear(), ran.clear()
    res = k.ladder_block(ROOT, [])
    assert served == [] and ran == [] and res['ladder_26b']['skipped'] == 'done'


def test_ladder_isolation_breach_ends_the_session(monkeypatch, tmp_path):
    k = ladder_kernel(monkeypatch, tmp_path)

    def serve(kind, procs):
        raise k.IsolationBreach('reachable')
    monkeypatch.setattr(k, 'ladder_serve', serve)
    with pytest.raises(k.IsolationBreach):
        k.ladder_block(ROOT, [])
    assert not (k.RESULTS_DIR / 'ladder_e4b_main' / 'startup_failed.json').exists()


def test_ladder_incomplete_block_stops_the_order_and_requires_resume(monkeypatch, tmp_path):
    k = ladder_kernel(monkeypatch, tmp_path)
    monkeypatch.setattr(k, 'ladder_serve', lambda kind, procs: {'ok': True})
    ran = []

    def run(code, mode, name, extra):
        ran.append(name)
        fake_rows(k, name, n=60)              # stopped half way (e.g. session margin)
        return {'rc': 0}
    monkeypatch.setattr(k, 'run_block', run)
    k.ladder_block(ROOT, [])
    assert ran == ['ladder_e4b_main'] and not k.ladder_may_start(1)
    assert k.ladder_status({'ok': True}) == 'requires_resume'
    assert k.x3_status({'ok': True}) == 'requires_resume'


def test_ladder_serve_checks_hashes_starts_twice_and_rechecks_isolation(monkeypatch, tmp_path):
    k = ladder_kernel(monkeypatch, tmp_path)
    dest = tmp_path / 'm'
    dest.mkdir()
    monkeypatch.setattr(k, 'model_path', lambda: dest)
    monkeypatch.setattr(k, 'model_hash_check', lambda: {'all_match': True})
    frees = []
    monkeypatch.setattr(k, 'ladder_free_gpu', lambda: frees.append(1) or {'used_mib': 0})
    monkeypatch.setattr(k, 'ladder_free_socket', lambda: {'killed': [], 'removed_stale_socket': False})
    tries = []

    def start(tp, gpus, port, tag, extra=()):
        tries.append(list(extra))
        if '--max-num-seqs' not in extra:
            raise RuntimeError('CUDA out of memory')
        k.SERVED[port] = str(dest)
        return object(), 12.0, list(extra)
    monkeypatch.setattr(k, 'start_server', start)
    monkeypatch.setattr(k, 'server_unreachable', lambda: {'ok': True})
    monkeypatch.setattr(k, 'code_dir', lambda: ROOT)
    toy = {'ok': True, 'rows': 6}
    monkeypatch.setattr(k, 'ladder_toy', lambda code, kind: dict(toy))
    out = k.ladder_serve('26b_a4b', [])
    log = [json.loads(x) for x in (k.RESULTS_DIR / k.LADDER_LOG).read_text().splitlines()]
    assert log[0]['model'] == '26b_a4b' and log[0]['toy']['ok'] and log[0]['extra_args'][-2:] == ['--max-num-seqs', '32']
    assert out['start_errors'][0]['error'].startswith('RuntimeError: CUDA out of memory')
    assert len(frees) == 2 and len(out['gpu_freed']) == 2      # before the start and after the failed try
    toy['ok'] = False
    with pytest.raises(RuntimeError, match='toy check failed'):
        k.ladder_serve('26b_a4b', [])
    toy['ok'] = True
    assert tries[0][:2] == ['--uds', str(k.UDS)] and tries[1][-2:] == ['--max-num-seqs', '32']
    assert k.R['verified_revision'] == k.MODEL_SPECS['26b_a4b']['revision'] and out['load_seconds'] == 12.0
    monkeypatch.setattr(k, 'server_unreachable', lambda: {'ok': False})
    with pytest.raises(k.IsolationBreach):
        k.ladder_serve('26b_a4b', [])
    monkeypatch.setattr(k, 'model_hash_check', lambda: {'all_match': False})
    with pytest.raises(RuntimeError, match='do not match'):
        k.ladder_serve('e2b', [])


def test_ladder_runner_args_use_the_block_model(monkeypatch, tmp_path):
    k = ladder_kernel(monkeypatch, tmp_path)
    monkeypatch.setattr(k, 'UDS_DIR', tmp_path)
    monkeypatch.setattr(k, 'R', {'phases': {}, 'verified_revision': 'WRONG'})
    monkeypatch.setattr(k, 'CODE_COMMIT', 'c' * 40, raising=False)
    cmd = k.runner_cmd(ROOT, 'x3', k.RESULTS_DIR / 'ladder_e2b', ['--close-out'])
    args = (tmp_path / 'args_ladder_e2b').read_text().splitlines()
    assert args[args.index('--model') + 1] == k.MODEL_SPECS['e2b']['dest']
    assert args[args.index('--model-revision') + 1] == k.MODEL_SPECS['e2b']['revision']
    assert args[args.index('--environment-id') + 1] == LS.BLOCKS[1]['environment_id']
    assert cmd[:len(k.COLAB_NETNS)] == k.COLAB_NETNS


def test_ladder_close_out_only_started_blocks(monkeypatch, tmp_path):
    k = ladder_kernel(monkeypatch, tmp_path)
    monkeypatch.setattr(k, 'block_started', lambda n: n == 'ladder_26b')
    calls = []
    monkeypatch.setattr(k, 'run_block', lambda code, mode, name, extra: calls.append((name, extra)) or {})
    k.x3_close_out(ROOT)
    assert [c[0] for c in calls] == ['ladder_26b'] and '--close-out' in calls[0][1]


def test_ladder_build_bundles_followup(tmp_path):
    out = tmp_path / 'b'
    subprocess.run([sys.executable, str(ROOT / 'notebooks' / 'build_kernel.py'),
                    str(ROOT / 'notebooks' / 'pilot_l4'), '--out-dir', str(out),
                    '--define', 'PLATFORM=colab', '--define', 'MODE=ladder'], check=True, capture_output=True)
    src = (out / 'pilot_l4.py').read_text()
    ns = {}
    i = src.index('CODE_B64')
    exec(src[:src.index('\n', i) + 1], ns)
    names = set(tarfile.open(fileobj=io.BytesIO(base64.b64decode(ns['CODE_B64'])), mode='r:gz').getnames())
    assert 'followup/analyze_ladder.py' in names and 'followup/ladder_seal.py' in names
    assert any(n.startswith('notebooks/colab/kaggle_env/') for n in names)
    assert "MODE = 'ladder'" in src and "PLATFORM = 'colab'" in src


# ------------------------------------------------------------------ analysis (synthetic)
LM = {'environment_id': 'colab-A100|py3.12|vllm0.19.1|tp1|model:<block model tag>', 'stop_at_epoch': LS.STOP_AT_EPOCH,
      'blocks': [dict(b) for b in LS.BLOCKS]}
E4M = {'environment_id': 'e4', 'blocks': [{'name': 'e4b_main', 'spec': 'followup/bank_x3/spec_main.csv',
                                           'framings': ['N'], 'start_by_epoch': None}]}


def seals(manifest=None):
    if manifest == AN.MANIFEST:
        return X3M, X3SEAL
    if manifest == E.MANIFEST:
        return E4M, 'e' * 64
    return LM, LSEAL


def ladder_root(tmp_path, ran=('ladder_e4b_main', 'ladder_26b'), failed=('ladder_e2b',),
                W_of=lambda s: 1, status_of=None, revision_of=None, session_stop=1e6):
    root = tmp_path / 'results'
    sched = AN.scheduled('spec_main.csv', ('N',))
    t = 100.0
    for b in LS.BLOCKS:
        d = root / b['name']
        if b['name'] in failed:
            d.mkdir(parents=True, exist_ok=True)
            (d / 'startup_failed.json').write_text(json.dumps(
                {'block': b['name'], 'model': b['model'], 'revision': b['revision'], 'utc': 150.0,
                 'error': 'x'}))
            continue
        if b['name'] not in ran:
            continue
        rows = synth(sched, W_of)
        rev = (revision_of or {}).get(b['name'], b['revision'])
        for r in rows:
            r.update(model_revision=rev, environment_id=b['environment_id'], elapsed_seconds='1')
            if status_of:
                r.update(status_of(r))
        write(rows, d)
        (d / 'attempts.jsonl').write_text(''.join(
            json.dumps({'event': 'start', 'run_id': s['run_id'], 'utc': t}) + '\n' for s in sched))
        (d / 'manifest.json').write_text(json.dumps(
            {'environment_id': b['environment_id'], 'model_revision': rev, 'code_commit': 'c',
             'model_id': MODEL, 'schedule_sha256': R.schedule_digest(sched)}))
        t += 100.0
    root.mkdir(parents=True, exist_ok=True)
    (root / 'x3_sessions.jsonl').write_text(json.dumps(
        {'session': 1, 'manifest_sha256': LSEAL, 'code_commit': 'c', 'started_utc': 50.0,
         'stop_at': session_stop}) + '\n')
    return root


def e4b_d16_root(tmp_path):
    root = tmp_path / 'e4b' / 'results'
    sched = AN.scheduled('spec_main.csv', ('N',))
    rows = synth(sched, lambda s: 1 if s['mechanism'] != 'M3' else 0)
    for r in rows:
        r.update(model_revision=E.REVISION, environment_id='e4', elapsed_seconds='1')
    d = write(rows, root / 'e4b_main')
    (d / 'attempts.jsonl').write_text(''.join(
        json.dumps({'event': 'start', 'run_id': s['run_id'], 'utc': 1.0}) + '\n' for s in sched))
    (d / 'manifest.json').write_text(json.dumps(
        {'environment_id': 'e4', 'model_revision': E.REVISION, 'code_commit': 'c',
         'model_id': MODEL, 'schedule_sha256': R.schedule_digest(sched)}))
    (root / 'x3_sessions.jsonl').write_text(json.dumps(
        {'session': 1, 'manifest_sha256': 'e' * 64, 'code_commit': 'c'}) + '\n')
    return root


def run_ladder(tmp_path, monkeypatch, root, e4b=True):
    from followup import detect_x3 as DX
    monkeypatch.setattr(AN, 'verify_seal', seals)
    monkeypatch.setattr(AN, 'CLAIMS', tmp_path / 'claims')
    monkeypatch.setattr(DX, 'run', lambda rows, dirs, out, workers: {'stub': len(rows), 'out': str(out)})
    args = ['--results', str(root), '--x3-results', str(x3_root(tmp_path / 'x3')),
            '--out', str(tmp_path / 'o')]
    if e4b:
        args += ['--e4b-results', str(e4b_d16_root(tmp_path))]
    L.main(args)
    return json.loads((tmp_path / 'o' / 'ladder_report.json').read_text())


def test_ladder_end_to_end(tmp_path, monkeypatch):
    def status(r):          # a few W = 0 failing and a few W = 0 passing in M3
        t, p = r['template_id'], int(r['issue_paraphrase'])
        if r['mechanism'] == 'M3' and p == 1:
            return {'W': 0, 'F': 0}
        if r['mechanism'] == 'M3' and p == 2:
            return {'W': 0, 'F': 1}
        return {}
    rep = run_ladder(tmp_path, monkeypatch, ladder_root(tmp_path, status_of=status))
    assert rep['report_complete'] and rep['seal_sha256'] == LSEAL
    assert rep['models']['e2b']['outcome'] == 'startup_failed'
    assert rep['models']['e2b']['startup_failed']['error'] == 'x'
    m12 = rep['models']['26b_a4b']
    assert m12['floor']['met'] and m12['complete_templates'] == 30 and m12['vs_x3']['templates_paired'] == 30
    t = rep['ladder_table']['26b_a4b']['by_mechanism']['M3']
    assert (t['W1'], t['W0_tests_pass'], t['W0_tests_fail'], t['not_evaluable'], t['U']) == (20, 10, 10, 0, 20)
    assert t['F_given_W1'] == 1.0 and t['F_given_W0'] == 0.5 and t['status_counts'] == {'patch': 40}
    assert rep['ladder_table']['31b_x3']['pooled']['runs'] == 120
    assert rep['ladder_table']['e2b'] == {'label': 'Gemma 4 E2B', 'outcome': 'startup_failed'}
    assert rep['e4b_hosts']['templates_paired'] == 30 and rep['e4b_d16_comparator']['seal_sha256'] == 'e' * 64
    assert m12['detectors']['out'].endswith('detectors/26b_a4b') and Path(m12['detectors']['out']).is_absolute()
    assert rep['provenance']['blocks']['ladder_26b']['outcome'] == 'ran'


def test_ladder_floor_not_met_drops_comparison(tmp_path, monkeypatch):
    root = ladder_root(tmp_path, status_of=lambda r: {'status': 'no_patch', 'M': 0, 'W': 0, 'F': 0})
    rep = run_ladder(tmp_path, monkeypatch, root, e4b=False)
    assert rep['models']['26b_a4b']['vs_x3'] == {'compared': False, 'reason': 'capability floor not met'}
    t = rep['ladder_table']['26b_a4b']['pooled']      # no_patch is evaluable (M = 0, W = 0, F = 0)
    assert (t['evaluable'], t['W0_tests_fail'], t['not_evaluable']) == (120, 120, 0)
    assert rep['e4b_d16_comparator'] is None and 'e4b_hosts' not in rep


def test_ladder_provenance_refuses_wrong_revision_and_order(tmp_path, monkeypatch):
    monkeypatch.setattr(AN, 'verify_seal', seals)
    root = ladder_root(tmp_path, revision_of={'ladder_26b': AN.REVISION})
    with pytest.raises(SystemExit, match="sealed environment/model"):
        L.provenance(LM, LSEAL, root)
    root2 = ladder_root(tmp_path / 'b', ran=('ladder_26b',), failed=())
    with pytest.raises(SystemExit, match='never did'):
        L.provenance(LM, LSEAL, root2)
    root3 = ladder_root(tmp_path / 'c', ran=(), failed=())
    p = L.provenance(LM, LSEAL, root3)
    assert {b['outcome'] for b in p['blocks'].values()} == {'not_run'}


def test_ladder_single_run_claim(tmp_path, monkeypatch):
    root = ladder_root(tmp_path)
    run_ladder(tmp_path, monkeypatch, root, e4b=False)
    with pytest.raises(SystemExit, match='already ran'):
        run_ladder(tmp_path, monkeypatch, root, e4b=False)


def test_ladder_toy_criteria(monkeypatch, tmp_path):
    k = ladder_kernel(monkeypatch, tmp_path)
    monkeypatch.setattr(k, 'UDS_DIR', tmp_path / 'uds')
    monkeypatch.setattr(k, 'TOY_DIR', tmp_path / 'uds' / 'toy')
    seen = {}

    def run(code, mode, name, extra, hard_at=None, out_root=None):
        import time as _t
        assert hard_at is not None and hard_at - _t.time() <= k.TOY_HARD_S
        seen.update(mode=mode, name=name, out_root=out_root)
        d = out_root / name
        d.mkdir(parents=True, exist_ok=True)
        with open(d / 'runs.csv', 'w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=['run_id', 'status', 'tool_calls'])
            w.writeheader()
            w.writerows(rows)
        return {'rc': 0}
    monkeypatch.setattr(k, 'run_block', run)
    rows = [{'run_id': i, 'status': 'patch', 'tool_calls': 3 if i == 0 else 0} for i in range(6)]
    out = k.ladder_toy(ROOT, 'e2b')
    assert out['ok'] and seen == {'mode': 'runner_smoke', 'name': 'e2b', 'out_root': tmp_path / 'uds' / 'toy'}
    assert not str(seen['out_root']).startswith(str(k.RESULTS_DIR))     # never in the sealed results
    rows = [{'run_id': i, 'status': 'patch', 'tool_calls': 0} for i in range(6)]
    assert not k.ladder_toy(ROOT, 'e2b')['ok']                           # no tool call at all
    rows = [{'run_id': i, 'status': 'infra_failed' if i == 5 else 'patch', 'tool_calls': 1} for i in range(6)]
    assert not k.ladder_toy(ROOT, 'e2b')['ok']
    rows = rows[:5]
    assert not k.ladder_toy(ROOT, 'e2b')['ok']


def test_ladder_toy_runner_uses_the_selected_model(monkeypatch, tmp_path):
    k = ladder_kernel(monkeypatch, tmp_path)
    monkeypatch.setattr(k, 'UDS_DIR', tmp_path)
    monkeypatch.setattr(k, 'R', {'phases': {}})
    monkeypatch.setattr(k, 'CODE_COMMIT', 'c' * 40, raising=False)
    monkeypatch.setattr(k, 'LADDER_KIND', 'e2b')
    k.runner_cmd(ROOT, 'runner_smoke', tmp_path / 'toy' / 'e2b', [])
    args = (tmp_path / 'args_e2b').read_text().splitlines()
    assert args[args.index('--split') + 1] == 'pilot'
    assert args[args.index('--model-revision') + 1] == k.MODEL_SPECS['e2b']['revision']


def test_seal_records_model_files_and_server():
    src = (ROOT / 'followup' / 'ladder_seal.py').read_text()
    assert "'models': models" in src and "'toy_check': k.TOY_RULE" in src and "'startup_timeout_s': 1200" in src
    k = load_kernel()
    assert all(len(k.MODEL_SPECS[b['model']]['hf']) >= 6 for b in LS.BLOCKS)


def test_ladder_startup_failed_record_is_validated(tmp_path):
    root = ladder_root(tmp_path)
    f = root / 'ladder_e2b' / 'startup_failed.json'
    good = json.loads(f.read_text())
    L.provenance(LM | {'stop_at_epoch': LS.STOP_AT_EPOCH}, LSEAL, root)
    for bad in ({'model': '26b_a4b'}, {'revision': 'x' * 40}, {'utc': float('inf')}, {'utc': 4e9},
                {'utc': 250.0}):         # 250: after the next block's first start (200)
        f.write_text(json.dumps(good | bad))
        with pytest.raises(SystemExit):
            L.provenance(LM | {'stop_at_epoch': LS.STOP_AT_EPOCH}, LSEAL, root)


def test_ladder_gpu_must_be_released(monkeypatch, tmp_path):
    k = ladder_kernel(monkeypatch, tmp_path)
    killed = []
    state = {'used': 30000, 'pids': ['4242']}

    def sh(cmd):
        if 'compute-apps' in cmd:
            return '\n'.join(state['pids'])
        return str(state['used'])
    monkeypatch.setattr(k, 'sh', sh)
    monkeypatch.setattr(k.os, 'kill', lambda pid, sig: killed.append(pid) or state.update(used=10, pids=[]))
    monkeypatch.setattr(k.time, 'sleep', lambda s: None)
    out = k.ladder_free_gpu()
    assert killed == [4242] and out['used_mib'] == 10
    state.update(used=30000, pids=[])
    monkeypatch.setattr(k, 'GPU_FREE_WAIT_S', -1)
    with pytest.raises(k.GpuNotReleased):
        k.ladder_free_gpu()
    assert issubclass(k.GpuNotReleased, k.SessionFatal) and issubclass(k.IsolationBreach, k.SessionFatal)


def test_ladder_serves_only_hash_listed_files(monkeypatch, tmp_path):
    k = kernel(monkeypatch, tmp_path, MODE='ladder', LADDER_KIND='e2b')
    src = tmp_path / 'hf' / 'gemma-4-e2b@971342c'
    src.mkdir(parents=True)
    for n in list(k.HF_EXPECTED_E2B) + ['README.md', 'extra_model.safetensors', 'preprocessor_config.json']:
        (src / n).write_text(n)
    real = k.Path
    monkeypatch.setattr(k, 'Path', lambda p, *a: real(str(p).replace('/kaggle/input/hf', str(tmp_path / 'hf')), *a))
    monkeypatch.setitem(k.MODEL_SPECS['e2b'], 'dest', str(tmp_path / 'dest'))
    out = k.model_path()
    assert sorted(x.name for x in out.iterdir()) == sorted(k.HF_EXPECTED_E2B)
    assert 'processor_config.json' in k.HF_EXPECTED_E2B and 'processor_config.json' in k.HF_EXPECTED_E4B_HF
    assert 'processor_config.json' not in k.HF_EXPECTED_E4B          # D16's Kaggle check unchanged
    (tmp_path / 'hf' / 'gemma-4-26b-a4b@4d7ae49.failed').write_text('HTTP 503')
    monkeypatch.setattr(k, 'LADDER_KIND', '26b_a4b')
    with pytest.raises(FileNotFoundError, match='HTTP 503'):
        k.model_path()


def test_ladder_every_start_inside_a_session(tmp_path):
    root = ladder_root(tmp_path, session_stop=150.0)      # the 26B block started at 200
    with pytest.raises(SystemExit, match='outside its session'):
        L.provenance(LM, LSEAL, root)
    L.provenance(LM, LSEAL, ladder_root(tmp_path / 'ok'))


def test_ladder_e4b_hosts_need_both_floors(tmp_path, monkeypatch):
    def status(r):
        return {'status': 'no_patch', 'M': 0, 'W': 0, 'F': 0}
    root = ladder_root(tmp_path, ran=('ladder_e4b_main', 'ladder_26b'), status_of=status)
    rep = run_ladder(tmp_path, monkeypatch, root, e4b=True)
    assert rep['e4b_hosts']['compared'] is False and rep['e4b_hosts']['floors']['colab'] is False


def test_ladder_deferral_is_never_a_startup_failure(monkeypatch, tmp_path):
    k = ladder_kernel(monkeypatch, tmp_path)

    def serve(kind, procs):
        raise k.LadderDeferred('ready after the stop time')
    monkeypatch.setattr(k, 'ladder_serve', serve)
    res = k.ladder_block(ROOT, [])
    assert 'deferred' in res['ladder_e4b_main'] and 'ladder_e2b' not in res
    assert not (k.RESULTS_DIR / 'ladder_e4b_main' / 'startup_failed.json').exists()
    assert k.ladder_status({'ok': True}) == 'requires_resume'
    # an ordinary error after the stop time is deferred too
    monkeypatch.setattr(k, 'ladder_serve', lambda kind, procs: (_ for _ in ()).throw(RuntimeError('engine')))
    monkeypatch.setattr(k, 'stop_at', lambda: 0.0)
    monkeypatch.setattr(k, 'ladder_may_start', lambda i: True)
    res = k.ladder_block(ROOT, [])
    assert 'deferred' in res['ladder_e4b_main']
    assert not (k.RESULTS_DIR / 'ladder_e4b_main' / 'startup_failed.json').exists()


def test_ladder_bundle_equals_the_files_the_seal_lists(tmp_path):
    """The seal hashes git ls-tree of bundle_paths(EXTRA_PATHS) at HEAD minus OWN; the Colab
    ladder build must bundle exactly those files (plus the OWN manifests once committed)."""
    out = tmp_path / 'b'
    subprocess.run([sys.executable, str(ROOT / 'notebooks' / 'build_kernel.py'),
                    str(ROOT / 'notebooks' / 'pilot_l4'), '--out-dir', str(out),
                    '--define', 'PLATFORM=colab', '--define', 'MODE=ladder'], check=True, capture_output=True)
    src = (out / 'pilot_l4.py').read_text()
    ns = {}
    i = src.index('CODE_B64')
    exec(src[:src.index('\n', i) + 1], ns)
    t = tarfile.open(fileobj=io.BytesIO(base64.b64decode(ns['CODE_B64'])), mode='r:gz')
    files = {m.name for m in t.getmembers() if m.isfile()}
    from followup.x3_seal import bundle_paths, git
    listed = set(git('ls-tree', '-r', '--name-only', 'HEAD', '--', *bundle_paths(LS.EXTRA_PATHS)).decode().split())
    assert files - LS.OWN == listed - LS.OWN and len(files - LS.OWN) > 2000


def test_bootstrap_ladder_disables_the_colab_cache_and_needs_a_writable_input():
    boot = (ROOT / 'notebooks' / 'colab' / 'colab_bootstrap.py').read_text()
    body = boot[boot.index('def downloads('):boot.index('def place(')]
    assert body.index("os.environ['DISABLE_COLAB_CACHE'] = '1'") < body.index('import kagglehub')
    assert body.index('writable_input()') < body.index('import kagglehub')
    assert "umount -l" in boot and "/proc/mounts" in boot


# ------------------------------------------------------------------ D17b (ladder2)
def test_ladder_free_socket_kills_the_holder_and_removes_the_file(monkeypatch, tmp_path):
    k = ladder_kernel(monkeypatch, tmp_path)
    uds = tmp_path / 'vllm.sock'
    uds.write_text('')                        # the socket of D17 session 1
    monkeypatch.setattr(k, 'UDS', uds)
    alive = {101: [9999]}                     # pid -> socket inodes it holds
    monkeypatch.setattr(k, 'socket_holders', lambda path: sorted(p for p, i in alive.items() if i))
    killed = []
    monkeypatch.setattr(k.os, 'kill', lambda pid, sig: killed.append(pid) or alive.pop(pid))
    monkeypatch.setattr(k.time, 'sleep', lambda s: None)
    out = k.ladder_free_socket()
    assert killed == [101] and out == {'killed': [101], 'removed_stale_socket': True} and not uds.exists()
    assert k.ladder_free_socket() == {'killed': [], 'removed_stale_socket': False}
    alive[202] = [1]                          # a holder that survives SIGKILL ends the session
    monkeypatch.setattr(k.os, 'kill', lambda pid, sig: None)
    monkeypatch.setattr(k.time, 'time', iter([0, 0, 100, 100, 100]).__next__)
    with pytest.raises(k.SessionFatal, match='still held'):
        k.ladder_free_socket()


def test_socket_holders_reads_inodes_and_root_fds(monkeypatch, tmp_path):
    k = ladder_kernel(monkeypatch, tmp_path)
    proc = tmp_path / 'proc'
    (proc / 'net').mkdir(parents=True)
    (proc / 'net' / 'unix').write_text(
        'Num RefCount Protocol Flags Type St Inode Path\n'
        '0000: 00000002 00000000 00010000 0001 01 4242 /root/tgv/vllm.sock\n'
        '0000: 00000002 00000000 00010000 0001 01 5555 /other.sock\n')
    for pid, uid, link in ((101, 0, 'socket:[4242]'), (102, 1001, 'socket:[4242]'), (103, 0, 'socket:[5555]')):
        (proc / str(pid) / 'fd').mkdir(parents=True)
        (proc / str(pid) / 'status').write_text(f'Uid:\t{uid}\t{uid}\t{uid}\t{uid}\n')
        os_link = proc / str(pid) / 'fd' / '3'
        os_link.symlink_to(link)
    real = k.Path
    monkeypatch.setattr(k, 'Path', lambda p, *a: real(str(p).replace('/proc', str(proc), 1)) if str(p).startswith('/proc') else real(p, *a))
    assert k.socket_holders('/root/tgv/vllm.sock') == [101]
    # Sol: one unreadable descriptor never drops the process that holds the socket
    (proc / '101' / 'fd' / '0').symlink_to('pipe:[1]')
    real_readlink = k.os.readlink

    def readlink(fd):
        if str(fd).endswith('/101/fd/0'):
            raise PermissionError('fd 0')
        return real_readlink(fd)
    monkeypatch.setattr(k.os, 'readlink', readlink)
    assert k.socket_holders('/root/tgv/vllm.sock') == [101]
    (proc / 'net' / 'unix').unlink()          # an unreadable socket table ends the session
    with pytest.raises(k.SessionFatal, match='net/unix'):
        k.socket_holders('/root/tgv/vllm.sock')


def test_ladder_serve_frees_the_socket_before_every_attempt(monkeypatch, tmp_path):
    k = ladder_kernel(monkeypatch, tmp_path)
    dest = tmp_path / 'm'
    dest.mkdir()
    monkeypatch.setattr(k, 'model_path', lambda: dest)
    monkeypatch.setattr(k, 'model_hash_check', lambda: {'all_match': True})
    monkeypatch.setattr(k, 'ladder_free_gpu', lambda: {'used_mib': 0})
    order = []
    monkeypatch.setattr(k, 'ladder_free_socket', lambda: order.append('free') or {'killed': []})

    def start(tp, gpus, port, tag, extra=()):
        order.append('start')
        if '--max-num-seqs' not in extra:
            raise RuntimeError('OSError: [Errno 98] Address already in use')
        k.SERVED[port] = str(dest)
        return object(), 1.0, list(extra)
    monkeypatch.setattr(k, 'start_server', start)
    monkeypatch.setattr(k, 'server_unreachable', lambda: {'ok': True})
    monkeypatch.setattr(k, 'code_dir', lambda: ROOT)
    monkeypatch.setattr(k, 'ladder_toy', lambda code, kind: {'ok': True})
    out = k.ladder_serve('e2b', [])
    assert order == ['free', 'start', 'free', 'start'] and len(out['socket_freed']) == 2


def test_ladder_socket_that_cannot_be_removed_ends_the_session(monkeypatch, tmp_path):
    k = ladder_kernel(monkeypatch, tmp_path)

    class Sock:
        def unlink(self):
            raise PermissionError('read-only')

        def exists(self):
            return True

        def __str__(self):
            return '/root/tgv/vllm.sock'
    monkeypatch.setattr(k, 'UDS', Sock())
    real = k.Path
    empty = tmp_path / 'proc'
    empty.mkdir()
    monkeypatch.setattr(k, 'Path', lambda p, *a: real(str(empty)) if str(p) == '/proc' else real(p, *a))
    with pytest.raises(k.SessionFatal):
        k.ladder_free_socket()


def test_ladder2_seal_and_kernel_manifest_path(monkeypatch, tmp_path):
    from followup import ladder2_seal as L2
    assert [b['name'] for b in L2.BLOCKS] == ['ladder2_e2b_main', 'ladder2_26b']
    assert [b['model'] for b in L2.BLOCKS] == ['e2b', '26b_a4b']
    assert all(b['revision'] == {x['model']: x for x in LS.BLOCKS}[b['model']]['revision'] for b in L2.BLOCKS)
    assert L2.STOP_AT_EPOCH == 1794430800 and 'followup/ladder2_manifest.json' in L2.OWN
    assert 'followup/analyze_ladder2.py' in L2.ANALYSIS_PATHS
    k = kernel(monkeypatch, tmp_path, MODE='ladder')
    assert 'followup/ladder2_manifest.json.ots' in k.X3_OWN
    src = SCRIPT.read_text()
    assert "f'followup/{LADDER_SEAL}_manifest.json'" in src and "LADDER_SEAL = 'ladder'" in src
    import runpy
    g = runpy.run_path(str(ROOT / 'followup' / 'analyze_ladder2.py'), run_name='not_main')
    assert str(g['L'].MANIFEST).endswith('followup/ladder2_manifest.json')
    g['L'].MANIFEST = ROOT / 'followup' / 'ladder_manifest.json'          # restore for other tests
