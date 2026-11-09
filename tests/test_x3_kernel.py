"""D15 (x3) kernel mode: Colab only, sealed bundle, chained sessions, the time-only start rule of
the M3 ablation, close-out only after the stop time, and resume into the root-only results."""
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


def code_with_manifest(tmp_path, files, stop=2e9, start_by=1.9e9):
    code = tmp_path / 'code'
    for rel, data in files.items():
        (code / rel).parent.mkdir(parents=True, exist_ok=True)
        (code / rel).write_bytes(data)
    m = {'files': {rel: sha(d) for rel, d in files.items()}, 'environment_id': 'e',
         'stop_at_epoch': stop, 'm3_start_by_epoch': start_by}
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
    assert k.x3_verify(code)['files'] == 3
    for bad, match in (({'X3_MANIFEST_SHA256': '0' * 64}, 'manifest'),
                       ({'SCRIPT_SHA256': '0' * 64}, 'not the D15 script'),
                       ({'SESSION': '2'}, 'starts empty'),
                       ({'SESSION': '1', 'RESUME_SHA256': 'x' * 64}, 'starts empty'),
                       ({'SESSION': ''}, 'SESSION'),
                       ({'SHARD': '1/2'}, 'no shards')):
        k = load(monkeypatch, tmp_path, **{**ok, **bad})
        with pytest.raises(RuntimeError, match=match):
            k.x3_verify(code)
    (code / 'runner' / 'extra.py').write_text('x')
    k = load(monkeypatch, tmp_path, **ok)
    with pytest.raises(RuntimeError, match='extra'):
        k.x3_verify(code)


def blocks(main, m3=None):
    b = {'x3_main': {'session': {'scheduled': 360, 'completed': main}}}
    if m3 is not None:
        b['x3_m3'] = {'session': {'scheduled': 80, 'completed': m3}}
    return b


def test_m3_start_rule_is_time_only(monkeypatch, tmp_path):
    now = time.time()
    k = load(monkeypatch, tmp_path, MODE='x3', KERNEL_T0=now)
    k.X3.update({'stop_at_epoch': now + 7200, 'm3_start_by_epoch': now + 3600})
    k.R['blocks'] = blocks(359)
    assert not k.x3_m3_may_run()                          # main incomplete
    k.R['blocks'] = blocks(360)
    assert k.x3_m3_may_run()                              # complete before the start-by time
    k.X3['m3_start_by_epoch'] = now - 1
    assert not k.x3_m3_may_run()                          # too late to start
    (k.RESULTS_DIR / 'x3_m3').mkdir(parents=True)
    assert k.x3_m3_may_run()                              # started earlier: continues
    k.X3['stop_at_epoch'] = now - 1
    assert not k.x3_m3_may_run()                          # past the stop time: nothing starts


def test_x3_status(monkeypatch, tmp_path):
    now = time.time()
    k = load(monkeypatch, tmp_path, MODE='x3')
    k.X3.update({'stop_at_epoch': now + 7200, 'm3_start_by_epoch': now + 3600})
    k.R['blocks'] = blocks(200)
    assert k.x3_status({'ok': True}) == 'requires_resume'
    k.R['blocks'] = blocks(360)
    assert k.x3_status({'ok': True}) == 'requires_resume'    # ablation still due
    k.X3['m3_start_by_epoch'] = now - 1
    assert k.x3_status({'ok': True}) == 'complete'           # ablation not eligible
    (k.RESULTS_DIR / 'x3_m3').mkdir(parents=True)
    k.R['blocks'] = blocks(360, 40)
    assert k.x3_status({'ok': True}) == 'requires_resume'
    k.R['blocks'] = blocks(360, 80)
    assert k.x3_status({'ok': True}) == 'complete'
    k.X3['stop_at_epoch'] = now - 1
    assert k.x3_status({'ok': True}) == 'closed_at_deadline'
    assert k.x3_status({'ok': False}) == 'close_out_failed'


def test_stop_at_and_close_out_only_after_the_stop_time(monkeypatch, tmp_path):
    now = time.time()
    k = load(monkeypatch, tmp_path, MODE='x3', KERNEL_T0=now)
    k.X3.update({'stop_at_epoch': now + 600, 'm3_start_by_epoch': now})
    assert k.stop_at() == now + 600
    assert not k.x3_deadline_reached()
    k.X3['stop_at_epoch'] = now - 1
    assert k.x3_deadline_reached()
    calls = []
    monkeypatch.setattr(k, 'run_block', lambda code, mode, name, extra: calls.append((name, extra)) or {})
    (k.RESULTS_DIR / 'x3_main').mkdir(parents=True)
    k.x3_close_out(tmp_path)
    assert calls == [('x3_main', k.x3_args(tmp_path, 'x3_main') + ['--close-out'])]


def test_x3_args():
    import types
    k = types.SimpleNamespace()
    spec = importlib.util.spec_from_file_location('tg_kernel_x3b', SCRIPT)
    k = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(k)
    m = k.x3_args(Path('/c'), 'x3_main')
    assert m[m.index('--spec') + 1].endswith('followup/bank_x3/spec_main.csv') and '--framings' not in m
    a = k.x3_args(Path('/c'), 'x3_m3')
    assert a[a.index('--spec') + 1].endswith('spec_m3.csv') and a[a.index('--framings') + 1] == 'N'


def test_x3_chain(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path, MODE='x3', SESSION='1', X3_MANIFEST_SHA256='m' * 64)
    k.X3.update({'stop_at_epoch': time.time() + 600})
    k.RESULTS_DIR.mkdir(parents=True)
    e = k.x3_chain({'resumed_from': None})
    assert e['session'] == 1
    with pytest.raises(RuntimeError, match='start without'):
        k.x3_chain({})                                      # the log now exists
    k = load(monkeypatch, tmp_path, MODE='x3', SESSION='2', X3_MANIFEST_SHA256='m' * 64)
    k.X3.update({'stop_at_epoch': time.time() + 600})
    assert k.x3_chain({'parent_seal': {'kind': 'final'}})['session'] == 2
    k = load(monkeypatch, tmp_path, MODE='x3', SESSION='4', X3_MANIFEST_SHA256='m' * 64)
    k.X3.update({'stop_at_epoch': time.time() + 600})
    with pytest.raises(RuntimeError, match='chain broken'):
        k.x3_chain({})


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
