"""D15 (x3) kernel mode: Colab only, sealed bundle, chained sessions, the sealed blocks' time-only start rule, close-out only after the stop time, and resume into the root-only results."""
import hashlib
import importlib.util
import io
import json
import tarfile
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / 'notebooks' / 'pilot_l4' / 'pilot_l4.py'


def load(monkeypatch, tmp_path, **defs):
    s = importlib.util.spec_from_file_location('tg_kernel_x3', SCRIPT)
    k = importlib.util.module_from_spec(s)
    s.loader.exec_module(k)
    monkeypatch.setattr(k, 'OUT', tmp_path / 'r.json')
    monkeypatch.setattr(k, 'RESULTS_DIR', tmp_path / 'tgv' / 'results')
    monkeypatch.setattr(k, 'CODE_COMMIT', 'c' * 40, raising=False)   # injected by build_kernel
    for n, v in defs.items():
        monkeypatch.setattr(k, n, v)
    return k


def sha(b):
    return hashlib.sha256(b).hexdigest()


def test_x3_is_colab_only(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path, MODE='x3')
    monkeypatch.setattr(k, 'sh', lambda c: 'NVIDIA L4, 23034 MiB\n' * 4 if 'nvidia-smi' in c else '')
    with pytest.raises(SystemExit, match='Colab only'):
        k.gpu_guard()
    assert 'x3' in k.COLAB_MODES


BLOCKS = [
    {'name': 'x3_main', 'spec': 'followup/bank_x3/spec_main.csv', 'framings': ['N', 'P', 'A'],
     'conditions': ['C'], 'runs': 360, 'start_by_epoch': None},
    {'name': 'x3_cw_m3', 'spec': 'followup/bank_x3/spec_cw_m3.csv', 'framings': ['N'],
     'conditions': ['CW'], 'runs': 28, 'start_by_epoch': 1.9e9},
    {'name': 'x3_m3', 'spec': 'followup/bank_x3/spec_m3.csv', 'framings': ['N'],
     'conditions': ['CNH', 'CL1'], 'runs': 80, 'start_by_epoch': 1.9e9},
    {'name': 'x3_cw_rest', 'spec': 'followup/bank_x3/spec_cw_rest.csv', 'framings': ['N'],
     'conditions': ['CW'], 'runs': 80, 'start_by_epoch': 1.9e9},
]


def with_blocks(k, stop, start_by):
    bl = [dict(b, start_by_epoch=None if b['start_by_epoch'] is None else start_by) for b in BLOCKS]
    k.X3.update({'stop_at_epoch': stop, 'blocks': bl, 'environment_id': 'e'})
    return bl


def code_with_manifest(tmp_path, files, stop=2e9, blocks=BLOCKS):
    code = tmp_path / 'code'
    for rel, data in files.items():
        (code / rel).parent.mkdir(parents=True, exist_ok=True)
        (code / rel).write_bytes(data)
    m = {'files': {rel: sha(d) for rel, d in files.items()}, 'environment_id': 'e',
         'stop_at_epoch': stop, 'blocks': blocks}
    raw = json.dumps(m).encode()
    (code / 'followup').mkdir(parents=True, exist_ok=True)
    (code / 'followup' / 'x3_manifest.json').write_bytes(raw)
    return code, sha(raw), m


def test_x3_verify_bundle_and_session_rules(monkeypatch, tmp_path):
    files = {'notebooks/pilot_l4/pilot_l4.py': b'script', 'followup/bank_x3/a.txt': b'a',
             'runner/runner.py': b'r'}
    code, msha, _ = code_with_manifest(tmp_path, files)
    ok = dict(MODE='x3', X3_MANIFEST_SHA256=msha, SCRIPT_SHA256=sha(b'script'), SESSION='1',
              RESUME_SHA256='', SHARD='')
    k = load(monkeypatch, tmp_path, **ok)
    v = k.x3_verify(code)
    assert v['files'] == 3 and v['blocks'] == [b['name'] for b in BLOCKS]
    for bad, match in (({'X3_MANIFEST_SHA256': '0' * 64}, 'manifest'),
                       ({'SCRIPT_SHA256': '0' * 64}, 'not the D15 script'),
                       ({'SESSION': '2'}, 'starts empty'),
                       ({'SESSION': '1', 'RESUME_SHA256': 'x' * 64}, 'starts empty'),
                       ({'SESSION': ''}, 'SESSION'),
                       ({'SHARD': '1/2'}, 'no shards')):
        k = load(monkeypatch, tmp_path, **{**ok, **bad})
        with pytest.raises(RuntimeError, match=match):
            k.x3_verify(code)
    # the main block must come first, without a start-by time
    for blocks in (BLOCKS[1:], [dict(BLOCKS[0], start_by_epoch=1.0)] + BLOCKS[1:]):
        code2, msha2, _ = code_with_manifest(tmp_path / 'b', files, blocks=blocks)
        k = load(monkeypatch, tmp_path, **{**ok, 'X3_MANIFEST_SHA256': msha2})
        with pytest.raises(RuntimeError, match='main block comes first'):
            k.x3_verify(code2)
    (code / 'runner' / 'extra.py').write_text('x')
    k = load(monkeypatch, tmp_path, **ok)
    with pytest.raises(RuntimeError, match='extra'):
        k.x3_verify(code)


def done(k, **completed):
    """R['blocks'] as run_block leaves it: scheduled and completed per block."""
    runs = {b['name']: b['runs'] for b in BLOCKS}
    k.R['blocks'] = {n: {'session': {'scheduled': runs[n], 'completed': c}}
                     for n, c in completed.items()}


def start(k, name, utc=None):
    d = k.RESULTS_DIR / name
    d.mkdir(parents=True, exist_ok=True)
    with open(d / 'attempts.jsonl', 'a') as f:
        f.write(json.dumps({'event': 'start', 'utc': utc or time.time()}) + '\n')


def test_start_rule_is_time_only_and_in_sealed_order(monkeypatch, tmp_path):
    now = time.time()
    k = load(monkeypatch, tmp_path, MODE='x3', KERNEL_T0=now)
    with_blocks(k, now + 7200, now + 3600)
    done(k, x3_main=359)
    assert k.x3_may_start(0) and not k.x3_may_start(1)    # main incomplete: nothing else starts
    done(k, x3_main=360)
    assert k.x3_may_start(1) and not k.x3_may_start(2)    # in order: CW-M3 before the ablation
    done(k, x3_main=360, x3_cw_m3=28)
    assert k.x3_may_start(2) and k.x3_m3_may_run() and not k.x3_may_start(3)
    for b in k.X3['blocks'][1:]:
        b['start_by_epoch'] = now - 1
    assert not k.x3_may_start(2)                          # too late to start
    (k.RESULTS_DIR / 'x3_m3').mkdir(parents=True)
    (k.RESULTS_DIR / 'x3_m3' / 'manifest.json').write_text('{}')
    assert not k.x3_may_start(2)          # Argon: a directory without a started run is not a start
    start(k, 'x3_m3', now - 10)
    assert k.x3_may_start(2) and k.first_start_utc('x3_m3') == now - 10   # started: continues
    k.X3['stop_at_epoch'] = now - 1
    assert not k.x3_may_start(0) and not k.x3_may_start(2)   # past the stop time: nothing starts


def test_x3_block_runs_in_order_and_bounds_first_launch(monkeypatch, tmp_path):
    """A block not yet started gets the runner's --stop-at at its start_by (no run starts after
    it, the race of Astra/Sol); a started one continues to the stop time; an incomplete block
    stops the loop."""
    now = time.time()
    k = load(monkeypatch, tmp_path, MODE='x3', KERNEL_T0=now)
    with_blocks(k, now + 7200, now + 3600)
    calls = []

    def fake(code, mode, name, extra):
        calls.append((name, extra))
        start(k, name)
        n = {b['name']: b['runs'] for b in BLOCKS}[name]
        k.R.setdefault('blocks', {})[name] = {'session': {'scheduled': n, 'completed': n}}
        return {}
    monkeypatch.setattr(k, 'run_block', fake)
    res = k.x3_block(tmp_path)
    assert [c[0] for c in calls] == [b['name'] for b in BLOCKS]
    assert '--stop-at' not in calls[0][1]
    for name, extra in calls[1:]:
        assert extra[extra.index('--stop-at') + 1] == str(min(now + 7200, now + 3600))
    assert set(res) == {b['name'] for b in BLOCKS}
    # main incomplete: the loop stops after it
    k = load(monkeypatch, tmp_path / 'z', MODE='x3', KERNEL_T0=now)
    monkeypatch.setattr(k, 'RESULTS_DIR', tmp_path / 'z' / 'results')
    with_blocks(k, now + 7200, now + 3600)
    calls.clear()

    def partial(code, mode, name, extra):
        calls.append(name)
        k.R.setdefault('blocks', {})[name] = {'session': {'scheduled': 360, 'completed': 100}}
        return {}
    monkeypatch.setattr(k, 'run_block', partial)
    k.x3_block(tmp_path)
    assert calls == ['x3_main']


def test_x3_status(monkeypatch, tmp_path):
    now = time.time()
    k = load(monkeypatch, tmp_path, MODE='x3')
    with_blocks(k, now + 7200, now + 3600)
    done(k, x3_main=200)
    assert k.x3_status({'ok': True}) == 'requires_resume'
    done(k, x3_main=360)
    assert k.x3_status({'ok': True}) == 'requires_resume'    # next block still due
    for b in k.X3['blocks'][1:]:
        b['start_by_epoch'] = now - 1
    assert k.x3_status({'ok': True}) == 'complete'           # no later block may start
    (k.RESULTS_DIR / 'x3_cw_m3').mkdir(parents=True)
    assert k.x3_status({'ok': True}) == 'complete'           # created, never started
    start(k, 'x3_cw_m3')
    done(k, x3_main=360, x3_cw_m3=10)
    assert k.x3_status({'ok': True}) == 'requires_resume'    # started: runs on
    done(k, x3_main=360, x3_cw_m3=28)
    assert k.x3_status({'ok': True}) == 'complete'
    k.X3['stop_at_epoch'] = now - 1
    assert k.x3_status({'ok': True}) == 'closed_at_deadline'
    assert k.x3_status({'ok': False}) == 'close_out_failed'


def test_stop_at_and_close_out_only_after_the_stop_time(monkeypatch, tmp_path):
    now = time.time()
    k = load(monkeypatch, tmp_path, MODE='x3', KERNEL_T0=now)
    with_blocks(k, now + 600, now)
    assert k.stop_at() == now + 600
    assert not k.x3_deadline_reached()
    k.X3['stop_at_epoch'] = now - 1
    assert k.x3_deadline_reached()
    calls = []
    monkeypatch.setattr(k, 'run_block', lambda code, mode, name, extra: calls.append((name, extra)) or {})
    (k.RESULTS_DIR / 'x3_m3').mkdir(parents=True)             # created but never started
    k.x3_close_out(tmp_path)
    assert calls == [('x3_main', k.x3_args(tmp_path, 'x3_main') + ['--close-out'])]
    start(k, 'x3_m3')
    calls.clear()
    k.x3_close_out(tmp_path)
    assert [c[0] for c in calls] == ['x3_main', 'x3_m3']


def test_x3_args(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path, MODE='x3')
    with_blocks(k, 2e9, 1.9e9)
    m = k.x3_args(Path('/c'), 'x3_main')
    assert m[m.index('--spec') + 1] == '/c/followup/bank_x3/spec_main.csv' and '--framings' not in m
    assert m[m.index('--bank') + 1] == '/c/followup/bank_x3/templates'
    for name, spec in (('x3_m3', 'spec_m3.csv'), ('x3_cw_m3', 'spec_cw_m3.csv'),
                       ('x3_cw_rest', 'spec_cw_rest.csv')):
        a = k.x3_args(Path('/c'), name)
        assert a[a.index('--spec') + 1].endswith(spec) and a[a.index('--framings') + 1] == 'N'


def test_x3_chain(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path, MODE='x3', SESSION='1', X3_MANIFEST_SHA256='m' * 64)
    with_blocks(k, time.time() + 600, time.time())
    k.RESULTS_DIR.mkdir(parents=True)
    e = k.x3_chain({'resumed_from': None})
    assert e['session'] == 1
    with pytest.raises(RuntimeError, match='start without'):
        k.x3_chain({})                                      # the log now exists
    k = load(monkeypatch, tmp_path, MODE='x3', SESSION='2', X3_MANIFEST_SHA256='m' * 64)
    with_blocks(k, time.time() + 600, time.time())
    assert k.x3_chain({'parent_seal': {'kind': 'final'}})['session'] == 2
    k = load(monkeypatch, tmp_path, MODE='x3', SESSION='4', X3_MANIFEST_SHA256='m' * 64)
    with_blocks(k, time.time() + 600, time.time())
    with pytest.raises(RuntimeError, match='chain broken'):
        k.x3_chain({})
    k = load(monkeypatch, tmp_path, MODE='x3', SESSION='3', X3_MANIFEST_SHA256='o' * 64)
    with_blocks(k, time.time() + 600, time.time())
    with pytest.raises(RuntimeError, match='chain broken'):
        k.x3_chain({})                                      # another seal's archive


def test_session_log_survives_seal_and_restore(monkeypatch, tmp_path):
    """Full cycle (Astra/Sol): session 1 writes its chain entry and seals with the kernel's own
    _snapshot_and_seal; session 2 restores that archive and chains to it."""
    import tempfile as tf
    work = tmp_path / 'working'
    work.mkdir()
    real_mkstemp, real_mkdtemp, real_open = tf.mkstemp, tf.mkdtemp, __import__('os').open
    monkeypatch.setattr(tf, 'mkstemp', lambda **kw: real_mkstemp(**{**kw, 'dir': str(work)}))
    monkeypatch.setattr(tf, 'mkdtemp', lambda **kw: real_mkdtemp(**{**kw, 'dir': str(work)}))
    k = load(monkeypatch, tmp_path, MODE='x3', SESSION='1', X3_MANIFEST_SHA256='m' * 64,
             SEALED=work / 'results_sealed.tar.gz')
    monkeypatch.setattr(k.os, 'open', lambda p, *a, **kw: real_open(str(work) if p == '/kaggle/working' else p, *a, **kw))
    with_blocks(k, time.time() + 600, time.time())
    k.RESULTS_DIR.mkdir(parents=True)
    k.x3_chain({})
    start(k, 'x3_main')
    digest = k._snapshot_and_seal('final')
    raw = (work / 'results_sealed.tar.gz').read_bytes()
    assert digest == sha(raw)
    names = tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz').getnames()
    assert 'results/x3_sessions.jsonl' in names and 'results/x3_main/attempts.jsonl' in names
    k2 = load(monkeypatch, tmp_path / 's2', MODE='x3', SESSION='2', X3_MANIFEST_SHA256='m' * 64,
              RESUME_SHA256=sha(raw))
    monkeypatch.setattr(k2, 'RESULTS_DIR', tmp_path / 's2' / 'tgv' / 'results')
    monkeypatch.setattr(k2.glob, 'glob', lambda *a, **kw: [str(work / 'results_sealed.tar.gz')])
    with_blocks(k2, time.time() + 600, time.time())
    restored = k2.restore_previous()
    assert restored['parent_seal']['kind'] == 'final'
    assert k2.x3_chain(restored)['session'] == 2 and k2.block_started('x3_main')


def test_hang_watch_stops_the_runner(monkeypatch, tmp_path):
    """A server that stops answering /health (the gemma4 parser loop) ends the block within
    HANG_FAILS probes: runner killed, agents killed, the block raises (the session seals and
    resumes), instead of letting every later run end as budget_exhausted."""
    import sys
    k = load(monkeypatch, tmp_path, MODE='x3', HANG_PROBE_S=0.2, HANG_FAILS=3)
    killed = []
    monkeypatch.setattr(k, 'runner_cmd', lambda *a: [sys.executable, '-c', 'import time; time.sleep(60)'])
    monkeypatch.setattr(k, 'sh', lambda c: killed.append(c) or '')
    monkeypatch.setattr(k, 'save', lambda: None)
    monkeypatch.setattr(k, 'checkpoint', lambda: None)
    monkeypatch.setattr(k, 'server_healthy', lambda: False)
    t0 = time.time()
    with pytest.raises(RuntimeError, match='stopped answering'):
        k.run_block(tmp_path, 'x3', 'x3_main', [])
    assert time.time() - t0 < 15
    hang = k.R['blocks']['x3_main']['server_hang']
    assert hang['fired_utc'] and hang['failures'] == 3
    assert {c.split()[-1] for c in killed} == set(k.AGENTS + k.EVALS)


def test_hang_watch_quiet_when_healthy(monkeypatch, tmp_path):
    import sys
    k = load(monkeypatch, tmp_path, MODE='x3', HANG_PROBE_S=0.1, HANG_FAILS=2)
    monkeypatch.setattr(k, 'runner_cmd', lambda *a: [sys.executable, '-c', 'import time; time.sleep(1)'])
    monkeypatch.setattr(k, 'sh', lambda c: '')
    monkeypatch.setattr(k, 'save', lambda: None)
    monkeypatch.setattr(k, 'checkpoint', lambda: None)
    flips = iter([False, True] * 50)
    monkeypatch.setattr(k, 'server_healthy', lambda: next(flips))   # never 2 failures in a row
    res = k.run_block(tmp_path, 'x3', 'x3_main', [])
    assert res['rc'] == 0 and 'server_hang' not in res
    assert 'x3' in k.HANG_WATCH_MODES and 'pilot' not in k.HANG_WATCH_MODES


def test_resume_extracts_into_the_results_parent(monkeypatch, tmp_path):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode='w:gz') as t:
        for name, data in (('results/x3_main/runs.csv', b'x'), ('results/seal.json', b'{"kind": "final"}')):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            t.addfile(info, io.BytesIO(data))
    arch = tmp_path / 'in' / 'results_sealed.tar.gz'
    arch.parent.mkdir()
    arch.write_bytes(buf.getvalue())
    k = load(monkeypatch, tmp_path, MODE='x3', RESUME_SHA256=sha(buf.getvalue()))
    monkeypatch.setattr(k.glob, 'glob', lambda *a, **kw: [str(arch)])
    out = k.restore_previous()
    assert (k.RESULTS_DIR / 'x3_main' / 'runs.csv').read_bytes() == b'x'
    assert out['parent_seal'] == {'kind': 'final'} and not (k.RESULTS_DIR / 'seal.json').exists()


def test_x3_build_bundles_followup_and_kaggle_env(tmp_path):
    """build_kernel adds followup/ for MODE=x3 (and the Kaggle lock for Colab); other builds
    are unchanged."""
    import base64
    import subprocess
    import sys

    def names(*defs):
        out = tmp_path / ('o' + str(len(defs)))
        subprocess.run([sys.executable, str(ROOT / 'notebooks' / 'build_kernel.py'),
                        str(ROOT / 'notebooks' / 'pilot_l4'), '--out-dir', str(out),
                        *[x for d in defs for x in ('--define', d)]], check=True, capture_output=True)
        src = (out / 'pilot_l4.py').read_text()
        ns = {}
        i = src.index('CODE_B64')
        exec(src[:src.index('\n', i) + 1], ns)
        return set(tarfile.open(fileobj=io.BytesIO(base64.b64decode(ns['CODE_B64'])), mode='r:gz').getnames())
    x3 = names('PLATFORM=colab', 'MODE=x3')
    assert 'followup/bank_x3/spec_main.csv' in x3 and 'followup/analyze_x3.py' in x3
    assert 'notebooks/colab/kaggle_env/lock_base.txt' in x3
    assert not any(n.startswith('followup') for n in names('PLATFORM=colab', 'MODE=runner_smoke'))
