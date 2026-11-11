"""D13: the kernel script's Colab platform (1x A100, TP=1, internet locked per uid). The Kaggle
platform (default) must behave as before; Colab refuses every mode but COLAB_MODES."""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / 'notebooks' / 'pilot_l4' / 'pilot_l4.py'


def load(monkeypatch, tmp_path, **defs):
    s = importlib.util.spec_from_file_location('tg_kernel_colab', SCRIPT)
    k = importlib.util.module_from_spec(s)
    s.loader.exec_module(k)
    monkeypatch.setattr(k, 'OUT', tmp_path / 'r.json')
    for n, v in defs.items():
        monkeypatch.setattr(k, n, v)
    return k


def fake_smi(monkeypatch, k, gpus, calls=None):
    def sh(cmd):
        if calls is not None:
            calls.append(cmd)
        if cmd.startswith('nvidia-smi --query-gpu=name,memory.total'):
            return '\n'.join(gpus)
        return ''
    monkeypatch.setattr(k, 'sh', sh)


L4X4 = ['NVIDIA L4, 23034 MiB'] * 4


def test_default_platform_is_kaggle_and_unchanged(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path)
    assert k.PLATFORM == 'kaggle'
    fake_smi(monkeypatch, k, L4X4)
    assert k.gpu_guard()['ok']
    fake_smi(monkeypatch, k, ['NVIDIA A100-SXM4-80GB, 81920 MiB'])
    with pytest.raises(SystemExit, match='GPU mismatch'):
        k.gpu_guard()
    monkeypatch.setattr(k, 'sh', lambda c: '4 NVIDIA L4')
    assert k.environment_id().startswith('kaggle-L4x4|')


@pytest.mark.parametrize('card', ['NVIDIA A100-SXM4-40GB, 40960 MiB', 'NVIDIA A100-SXM4-80GB, 81920 MiB'])
def test_colab_accepts_one_a100_40_or_80(monkeypatch, tmp_path, card):
    k = load(monkeypatch, tmp_path, PLATFORM='colab', MODE='runner_smoke')
    fake_smi(monkeypatch, k, [card])
    assert k.gpu_guard()['ok'] and k.R['colab_gpu'] == card
    assert k.environment_id() == 'colab-A100|py3.12|vllm0.19.1|tp1|model:52f3f65-overlay'


def test_colab_refuses_other_gpus_and_frozen_modes(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path, PLATFORM='colab', MODE='runner_smoke')
    fake_smi(monkeypatch, k, L4X4)
    with pytest.raises(SystemExit, match='one A100'):
        k.gpu_guard()
    for mode in ('confirmatory', 'pilot', 'x1_calibration', 'x1_transfer', 'eval_check'):
        k2 = load(monkeypatch, tmp_path, PLATFORM='colab', MODE=mode)
        fake_smi(monkeypatch, k2, ['NVIDIA A100-SXM4-80GB, 81920 MiB'])
        with pytest.raises(SystemExit, match='never runs on Colab'):
            k2.gpu_guard()


def test_colab_netns_check_fails_closed(monkeypatch, tmp_path):
    """Colab refuses iptables even to root: isolation is an empty network namespace, checked
    (only a down loopback; an agent uid inside reaches nothing) and fail closed."""
    k = load(monkeypatch, tmp_path, PLATFORM='colab')
    calls = []

    LO = '1: lo: <LOOPBACK> mtu 65536 qdisc noop state DOWN mode DEFAULT group default qlen 1000\\    link/loopback 00:00:00:00:00:00'

    def sh(cmd, links='lo', ip=LO, rc='3'):
        calls.append(cmd)
        if '/proc/net/dev' in cmd:
            return links
        if 'ip -o link show' in cmd:
            return ip
        return rc
    monkeypatch.setattr(k, 'sh', sh)
    out = k.colab_netns_check()
    assert out['links'] == ['lo'] and out['method'].startswith('netns+ipc')
    probes = [c for c in calls if 'b64decode' in c]
    assert len(probes) == 3 and all(c.startswith('unshare --net --ipc -- setpriv --reuid=tgagent0') for c in probes)
    assert all(c.startswith('unshare --net --ipc -- ') for c in calls)
    UP = LO.replace('<LOOPBACK>', '<LOOPBACK,UP,LOWER_UP>').replace('state DOWN', 'state UNKNOWN')
    for kw, match in (({'links': 'lo\neth0'}, 'not empty'), ({'ip': UP}, 'not empty'),
                      ({'ip': LO + '\n2: eth0: <BROADCAST> state DOWN'}, 'not empty'),
                      ({'rc': '0'}, 'not denied'), ({'rc': '4'}, 'not denied'),   # refused/other != unreachable
                      ({'rc': '127'}, 'not denied')):
        monkeypatch.setattr(k, 'sh', lambda c, kw=kw: sh(c, **kw))
        with pytest.raises(RuntimeError, match=match):
            k.colab_netns_check()


def test_colab_runner_and_probes_run_in_a_network_namespace(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path, PLATFORM='colab')
    seen = []
    monkeypatch.setattr(k, 'sh', lambda c: seen.append(c) or '1')
    k.as_user('tgagent0', 'ls /')
    assert seen[0].startswith('unshare --net --ipc -- setpriv --reuid=tgagent0')
    kg = load(monkeypatch, tmp_path)                    # Kaggle: unchanged
    seen.clear()
    monkeypatch.setattr(kg, 'sh', lambda c: seen.append(c) or '1')
    kg.as_user('tgagent0', 'ls /')
    assert seen[0].startswith('setpriv --reuid=tgagent0')
    src = SCRIPT.read_text()
    rc = src.split('def runner_cmd(')[1].split('\ndef ')[0]
    assert "(COLAB_NETNS + cmd) if PLATFORM == 'colab' else cmd" in rc
    assert k.COLAB_NETNS == ['unshare', '--net', '--ipc', '--']


def test_colab_isolation_probes_include_the_network(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path, PLATFORM='colab')
    for name in ('net_tcp_ext', 'net_dns_https', 'net_metadata', 'net_lo_tcp', 'content_ls'):
        assert name in k.COLAB_DENIED
    src = SCRIPT.read_text()
    iso = src.split("def isolation(code):")[1].split('\ndef ')[0]
    assert "out['net_lock'] = colab_netns_check()" in iso and 'probes.update(COLAB_DENIED)' in iso
    assert "out['hide'] = colab_hide()" in iso
    su = src.split('def server_unreachable():')[1].split('\ndef ')[0]
    assert "PLATFORM == 'colab' and reach" in su       # any TCP reach aborts on Colab
    assert 'if failures:' in iso                     # every probe that succeeds aborts the run


def test_notebook_embeds_the_bootstrap(tmp_path):
    import subprocess
    import sys
    subprocess.run([sys.executable, str(ROOT / 'notebooks' / 'colab' / 'make_notebook.py')], check=True)
    nb = json.loads((ROOT / 'notebooks' / 'colab' / 'twinguard_colab.ipynb').read_text())
    boot = (ROOT / 'notebooks' / 'colab' / 'colab_bootstrap.py').read_text()
    srcs = [c['source'] for c in nb['cells']]
    assert boot in srcs
    assert any("drive.mount('/root/drive')" in s for s in srcs)    # never under /content
    # credentials only from Colab secrets, never written into the notebook
    assert any("downloads(userdata.get('KAGGLE_USERNAME'), userdata.get('KAGGLE_KEY'), LADDER)" in s
               for s in srcs)


REQ = ''.join(f'{n}==1\n' for n in ('vllm', 'torch', 'transformers', 'numpy', 'pandas', 'pytest',
                                       'adk-submission'))


def _install_env(monkeypatch, tmp_path, k):
    import hashlib
    whl = tmp_path / 'kaggle' / 'input' / 'x' / 'gemma-4-developer-agent-wheelhouse' / 'v' / 'a-1-py3-none-any.whl'
    whl.parent.mkdir(parents=True, exist_ok=True)
    whl.write_bytes(b'wheel')
    h = hashlib.sha256(b'wheel').hexdigest()
    code = tmp_path / 'code'
    env = code / k.COLAB_ENV
    env.mkdir(parents=True, exist_ok=True)
    (env / 'lock_base.txt').write_text('numpy==1 \\\n    --hash=sha256:00\n')
    (env / 'kaggle_freeze.txt').write_text(
        f'a @ file:///tmp/wheelhouse/a-1-py3-none-any.whl#sha256={h}\n' + REQ)
    monkeypatch.setattr(k, 'code_dir', lambda: code)
    wh = tmp_path / 'wh'
    wh.mkdir(exist_ok=True)
    work = tmp_path / 'work'
    real_path = Path

    def fake_path(*a):
        if a == ('/tmp/wheelhouse',):
            return wh
        if a and str(a[0]).startswith('/kaggle/working'):
            return real_path(str(work) + str(a[0])[len('/kaggle/working'):], *a[1:])
        return real_path(*a)
    monkeypatch.setattr(k, 'Path', fake_path)
    monkeypatch.setattr(k.glob, 'glob', lambda pat, **kw: [str(whl)] if pat.endswith('*.whl') else [])
    monkeypatch.setattr(k.os, 'symlink', lambda src, dst: real_path(dst).write_bytes(real_path(src).read_bytes()))
    calls, state = [], {'freeze': ''}

    def run(cmd, **kw):
        calls.append(cmd)
        out = state['freeze'] if 'freeze' in cmd else ''
        return type('R', (), {'returncode': 0, 'stdout': out, 'stderr': ''})()
    monkeypatch.setattr(k.subprocess, 'run', run)
    return calls, state, h, work


def test_colab_install_replicates_kaggle(monkeypatch, tmp_path):
    """Colab installs Kaggle's package versions (hashed lock, --no-deps), then the wheelhouse files
    exactly as Kaggle, and must end with a freeze that is a subset of Kaggle's."""
    k = load(monkeypatch, tmp_path, PLATFORM='colab')
    calls, state, h, work = _install_env(monkeypatch, tmp_path, k)
    ok = f'a @ file:///tmp/wheelhouse/a-1-py3-none-any.whl#sha256={h}\n' + REQ + 'pip==26.0\n'
    for printed, freeze, err in (('0.19.1 2.10.0+cu128 5.13.1', ok, None),
                                 ('0.20.0 2.10.0+cu128 5.13.1', ok, 'versions differ'),
                                 ('0.19.1 2.10.0+cu128 5.13.1', ok + 'numpy==2.5.4\n', 'not as on Kaggle'),
                                 ('0.19.1 2.10.0+cu128 5.13.1', ok + 'extra==1\n', 'not as on Kaggle'),
                                 ('0.19.1 2.10.0+cu128 5.13.1', '', 'lacks required'),       # Sol P2
                                 ('0.19.1 2.10.0+cu128 5.13.1', 'pip==26.0\n', 'lacks required')):
        monkeypatch.setattr(k, 'sh', lambda c, p=printed: p if 'import vllm' in c else 'x')
        state['freeze'] = freeze
        calls.clear()
        if err is None:
            out = k.colab_install()
            assert out['versions_as_kaggle'] and out['not_as_on_kaggle'] == []
            assert (work / 'pip_freeze.txt').exists() and (work / 'install' / '1_lock.log').exists()
            lock, wheels = calls[:2]
            assert {'--no-deps', '--require-hashes', '-r'} <= set(lock)
            assert {'--no-deps', '--force-reinstall'} <= set(wheels) and '--require-hashes' not in wheels
            probe = calls[-1]
            assert probe[1] == '-c' and probe[3:] == list(k.COLAB_IMPORT_PROBE)
            assert out['imports_ok'] == list(k.COLAB_IMPORT_PROBE)
        else:
            with pytest.raises(RuntimeError, match=err):
                k.colab_install()


def test_colab_install_fails_on_a_missing_runtime_import(monkeypatch, tmp_path):
    """Smoke 3: vLLM's server imports uvloop, which no package declares. The install imports the
    serving modules and fails with the list, before any model or server work."""
    k = load(monkeypatch, tmp_path, PLATFORM='colab')
    calls, state, h, work = _install_env(monkeypatch, tmp_path, k)
    state['freeze'] = f'a @ file:///tmp/wheelhouse/a-1-py3-none-any.whl#sha256={h}\n' + REQ
    monkeypatch.setattr(k, 'sh', lambda c: '0.19.1 2.10.0+cu128 5.13.1' if 'import vllm' in c else 'x')

    def run(cmd, **kw):
        calls.append(cmd)
        if cmd[1] == '-c':
            return type('R', (), {'returncode': 1, 'stdout': "uvicorn.loops.uvloop: ModuleNotFoundError: No module named 'uvloop'", 'stderr': ''})()
        return type('R', (), {'returncode': 0, 'stdout': state['freeze'] if 'freeze' in cmd else '', 'stderr': ''})()
    monkeypatch.setattr(k.subprocess, 'run', run)
    with pytest.raises(RuntimeError, match="(?s)4_imports failed:.*uvloop"):
        k.colab_install()
    assert (work / 'install' / '4_imports.log').exists()


def test_colab_import_probe_code_runs(tmp_path):
    """The probe program itself: ok modules pass, a missing one is listed and exits 1."""
    import subprocess
    import sys
    spec = importlib.util.spec_from_file_location('tg_probe', ROOT / 'notebooks' / 'pilot_l4' / 'pilot_l4.py')
    k = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(k)
    ok = subprocess.run([sys.executable, '-c', k.COLAB_IMPORT_CODE, 'json', 'csv'], capture_output=True, text=True)
    assert ok.returncode == 0
    bad = subprocess.run([sys.executable, '-c', k.COLAB_IMPORT_CODE, 'json', 'no_such_mod_tg'], capture_output=True, text=True)
    assert bad.returncode == 1 and 'no_such_mod_tg: ModuleNotFoundError' in bad.stdout


def test_colab_install_rejects_a_wheel_kaggle_did_not_install(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path, PLATFORM='colab')
    calls, _, _, _ = _install_env(monkeypatch, tmp_path, k)
    env = tmp_path / 'code' / k.COLAB_ENV
    (env / 'kaggle_freeze.txt').write_text('a @ file:///tmp/wheelhouse/a-1-py3-none-any.whl#sha256=' + '0' * 64 + '\n')
    with pytest.raises(RuntimeError, match='wheelhouse files differ'):
        k.colab_install()
    assert calls == []                                  # nothing installed


def test_colab_install_requires_the_bundled_lock(monkeypatch, tmp_path):
    """Sol P1: a bundle without notebooks/colab/kaggle_env fails before pip, with a clear reason."""
    k = load(monkeypatch, tmp_path, PLATFORM='colab')
    calls, _, _, _ = _install_env(monkeypatch, tmp_path, k)
    (tmp_path / 'code' / k.COLAB_ENV / 'lock_base.txt').unlink()
    with pytest.raises(FileNotFoundError, match='not in the code bundle'):
        k.colab_install()
    assert calls == []


def test_colab_build_bundles_the_kaggle_env(tmp_path):
    """Sol P1: a PLATFORM=colab build carries the lock; a Kaggle build is unchanged."""
    import base64
    import io
    import subprocess
    import sys
    import tarfile

    def names(*defs):
        out = tmp_path / ('o' + str(len(defs)))
        subprocess.run([sys.executable, str(ROOT / 'notebooks' / 'build_kernel.py'),
                        str(ROOT / 'notebooks' / 'pilot_l4'), '--out-dir', str(out),
                        *[x for d in defs for x in ('--define', d)]], check=True, capture_output=True)
        src = (out / 'pilot_l4.py').read_text()
        ns = {}
        i = src.index('CODE_B64')
        exec(src[:src.index('\n', i) + 1], ns)
        tar = tarfile.open(fileobj=io.BytesIO(base64.b64decode(ns['CODE_B64'])), mode='r:gz')
        return set(tar.getnames())
    colab = names('PLATFORM=colab', 'MODE=runner_smoke')
    assert 'notebooks/colab/kaggle_env/lock_base.txt' in colab
    assert 'notebooks/colab/kaggle_env/kaggle_freeze.txt' in colab
    assert not any('kaggle_env' in n for n in names('MODE=runner_smoke'))


def test_kaggle_env_lock_matches_the_kaggle_freeze():
    """Every locked package is at the version the Kaggle image has; every lock entry is hashed."""
    import re
    env = ROOT / 'notebooks' / 'colab' / 'kaggle_env'
    norm = lambda n: re.sub(r'[-_.]+', '-', n).lower()
    kaggle = {}
    for line in (env / 'kaggle_freeze.txt').read_text().splitlines():
        if '==' in line and ' @ ' not in line:
            n, v = line.split('==')
            kaggle[norm(n)] = v.strip()
    blocks = re.split(r'\n(?=\S)', (env / 'lock_base.txt').read_text().strip())
    assert len(blocks) > 150
    for b in blocks:
        head = b.split()[0]
        n, v = head.split('==')
        assert kaggle.get(norm(n)) == v, head
        assert '--hash=sha256:' in b, head
    assert not any(norm(b.split('==')[0]).startswith('nvidia-cutlass') for b in blocks)
    # runtime-optional packages of the serving stack that Kaggle has and no package declares
    # (smoke 3: vLLM's server imports uvloop); present on Kaggle, so present here
    names = {norm(b.split('==')[0]) for b in blocks}
    assert {'uvloop', 'httptools', 'orjson', 'ujson', 'email-validator', 'xxhash', 'nvtx', 'optree',
            'opt-einsum'} <= names


def test_colab_secret_scan_flags_credentials_not_token_counts(tmp_path, monkeypatch):
    """Sol: `--token X`, `--NotebookApp.token X`, `KAGGLE_KEY=X`, `?token=X` and `--api-key X`
    are credentials; an empty token and vLLM's `--max-num-batched-tokens` are not."""
    import contextlib
    import io
    k = load(monkeypatch, tmp_path, PLATFORM='colab')
    cases = {'1': b'jupyter\0--NotebookApp.token\0abc', '2': b'jupyter\0--NotebookApp.token=',
             '3': b'vllm\0--max-num-batched-tokens\08192\0--thinking-token-budget\04096',
             '4': b'x\0KAGGLE_KEY=zz', '5': b'curl\0http://h/?token=q', '6': b'app\0--token\0--other',
             '7': b'app\0--api-key\0k1', '8': b'app\0--token\0secret',
             '9': b"curl\0http://h/?x=1&token=EXAMPLE", '10': b'curl\0http://h/?x=1&page=2'}
    for pid, c in cases.items():
        (tmp_path / pid).mkdir()
        (tmp_path / pid / 'cmdline').write_bytes(c)
    code = k.COLAB_SECRET_SCAN.replace("'/proc/[0-9]*/cmdline'", repr(str(tmp_path) + '/[0-9]*/cmdline'))
    code = code.replace("c.split('/')[2]", "c.split('/')[-2]")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        exec(code, {})
    assert buf.getvalue().split() == ['SCAN_OK', '1', '4', '5', '7', '8', '9']


def test_colab_hide_scans_as_agent_and_evaluator_and_aborts(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path, PLATFORM='colab')
    monkeypatch.setattr(k, 'sh', lambda c: '700' if 'stat' in c else '0')
    runs = []

    def fake_run(cmd, **kw):
        runs.append(cmd)
        out = 'SCAN_OK 4242' if f'--reuid={k.EVALS[0]}' in cmd else 'SCAN_OK'
        return type('R', (), {'returncode': 0, 'stdout': out, 'stderr': ''})()
    monkeypatch.setattr(k.subprocess, 'run', fake_run)
    with pytest.raises(RuntimeError, match='credentials or tokens'):
        k.colab_hide()
    assert len(runs) == 2 and runs[0][0] == 'setpriv' and f'--reuid={k.AGENTS[0]}' in runs[0]
    ok = lambda cmd, **kw: type('R', (), {'returncode': 0, 'stdout': 'SCAN_OK', 'stderr': ''})()
    monkeypatch.setattr(k.subprocess, 'run', ok)
    assert k.colab_hide()['cmdline_secret_pids'] == {}
    # Sol: a scanner that fails (rc 1, empty stdout) is never read as "no secrets"
    bad = lambda cmd, **kw: type('R', (), {'returncode': 1, 'stdout': '', 'stderr': 'boom'})()
    monkeypatch.setattr(k.subprocess, 'run', bad)
    with pytest.raises(RuntimeError, match='credential scan failed'):
        k.colab_hide()


def test_colab_unix_reach_uses_each_socket_type_and_abstract_names(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path, PLATFORM='colab')
    seen = []

    def as_user(u, cmd):
        seen.append((u, cmd))
        return '0' if 'SOCK_DGRAM' in cmd and u == k.EVALS[0] else '1'
    monkeypatch.setattr(k, 'as_user', as_user)
    reach = k.colab_unix_reach({('/run/a.sock', 1), ('/run/d.sock', 2), ('@abs', 5)})
    assert reach == [f'{k.EVALS[0]}:/run/d.sock:SOCK_DGRAM']
    assert any('SOCK_SEQPACKET' in c and '\\x00abs' in c for _, c in seen)
    assert {u for u, _ in seen} == {k.AGENTS[0], k.EVALS[0]}


def test_colab_capacity_fails_when_a_request_fails(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path, PLATFORM='colab')
    monkeypatch.setattr(k, 'long_prompt', lambda: [{'role': 'user', 'content': 'x'}])
    monkeypatch.setattr(k, 'kv_info', lambda tag: [])
    monkeypatch.setattr(k, 'sh', lambda c: '1 MiB, 2 MiB')
    good = {'choices': [{}], 'usage': {'completion_tokens': 10}}
    calls = []

    def chat(body, timeout=900):
        calls.append(1)
        return good if len(calls) != 3 else {'http_error': 500, 'body': 'oom'}
    monkeypatch.setattr(k, 'uds_chat', chat)
    with pytest.raises(RuntimeError, match='requests failed'):
        k.colab_capacity('tp1_8000')
    part = k.R['colab_capacity_partial']['conc_1']        # partial result kept (Sol)
    assert part['ok'] == 3 and part['errors'] and part['gpu_mem_peak_mib'] in (None, 1)


def test_bootstrap_sync_copies_install_logs(tmp_path, monkeypatch):
    """Sol: colab_install's pip logs (/kaggle/working/install/*.log) reach Drive."""
    spec = importlib.util.spec_from_file_location('cb', ROOT / 'notebooks' / 'colab' / 'colab_bootstrap.py')
    cb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cb)
    work = tmp_path / 'working'
    (work / 'install').mkdir(parents=True)
    (work / 'install' / '1_lock.log').write_text('pip log')
    (work / 'pilot_results.json').write_text('{}')
    real = cb.Path
    monkeypatch.setattr(cb, 'Path', lambda p, *a: work if p == '/kaggle/working' else real(p, *a))
    cb.sync(tmp_path / 'drive')
    assert (tmp_path / 'drive' / 'install_1_lock.log').read_text() == 'pip log'
    assert not list((tmp_path / 'drive').glob('.*.part'))


def test_colab_net_probe_classifies_outcomes(tmp_path):
    """The connect probe: 3 only for unreachable; a refused connection (lo up, nothing listening)
    is 4, i.e. NOT counted as denied."""
    import socket
    import subprocess
    import sys
    spec = importlib.util.spec_from_file_location('tg_np', SCRIPT)
    k = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(k)
    so = socket.socket(); so.bind(('127.0.0.1', 0)); port = so.getsockname()[1]; so.close()
    r = subprocess.run([sys.executable, '-I', '-c', k.COLAB_NET_PROBE, '127.0.0.1', str(port)])
    assert r.returncode == 4
    srv = socket.socket(); srv.bind(('127.0.0.1', 0)); srv.listen(1)
    r = subprocess.run([sys.executable, '-I', '-c', k.COLAB_NET_PROBE, '127.0.0.1', str(srv.getsockname()[1])])
    srv.close()
    assert r.returncode == 0


@pytest.mark.parametrize('total,util', [('40960', 0.9), ('81920', 0.45)])
def test_colab_vllm_budget_is_the_40gb_one(monkeypatch, tmp_path, total, util):
    """Astra/Sol: same absolute vLLM budget on the 40 and the 80 GB A100 (KV, batching,
    preemption as on 40 GB), recorded."""
    k = load(monkeypatch, tmp_path, PLATFORM='colab')
    monkeypatch.setattr(k, 'sh', lambda c: total if 'memory.total' in c else '')
    assert k.colab_gpu_util() == util
    assert k.R['colab_vllm_budget']['budget_mib'] == 36864
    monkeypatch.setattr(k, 'sh', lambda c: '16000' if 'memory.total' in c else '')
    with pytest.raises(RuntimeError, match='unexpected A100'):
        k.colab_gpu_util()
    src = SCRIPT.read_text()
    assert "gpu_memory_utilization=colab_gpu_util() if PLATFORM == 'colab' else 0.90" in src


def test_colab_net_probe_survives_the_as_user_shell_layers(monkeypatch, tmp_path):
    """The probe command as as_user builds it, run through the real shells (without unshare and
    setpriv, which need root): a closed local port gives 4, never a syntax error (1)."""
    import socket
    import subprocess
    k = load(monkeypatch, tmp_path, PLATFORM='kaggle')
    seen = []
    monkeypatch.setattr(k, 'sh', lambda c: seen.append(c) or '')
    so = socket.socket(); so.bind(('127.0.0.1', 0)); port = so.getsockname()[1]; so.close()
    k.as_user('tgagent0', k.colab_net_probe_cmd('127.0.0.1', port))
    cmd = seen[0].split(' -- ', 1)[1]                    # drop "setpriv ... --"
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    assert r.stdout.strip() == '4', (cmd, r.stdout, r.stderr)
