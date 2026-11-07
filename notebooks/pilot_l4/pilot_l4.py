"""TwinGuard pilot kernel (WP8): isolation setup, official serving, runner.
Derived from the WP1 smoke kernel.

TwinGuard WP1 smoke test on Kaggle L4x4 (offline). Kaggle script kernel.

Inputs (kernel-metadata.json): competition gemma-4-developer-agent, the official
wheelhouse dataset (vLLM 0.19.1 etc.), Kaggle Models google/gemma-4 31B QAT w4a16-ct v2,
and the repo code bundled into this script by notebooks/build_kernel.py.

Phases (each guarded; results always written to /kaggle/working/smoke_results.json):
  0 GPU guard (abort unless 4x L4)          4 throughput at concurrency 1/4/8/16
  1 wheel install (official procedure)      5 one real harness episode on the toy fixture
  2 vLLM TP=4 with the official flags       6 repeat 2-5 with two TP=2 servers (2x2)
  3 reasoning + tool-call parser checks     7 model files hashed vs Hugging Face 52f3f65
"""
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import traceback
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

OUT = Path('/kaggle/working/pilot_results.json')
MODE = 'runner_smoke'   # 'runner_smoke' (toy fixture, 6 runs) or 'pilot' (72 + 9 runs); build --define
KERNEL_T0 = time.time()
SESSION_LIMIT_S = 12 * 3600      # Kaggle GPU session limit
STOP_MARGIN_S = 90 * 60          # no run starts later than this before the limit (60 min budget + eval)
AGENTS = [f'tgagent{i}' for i in range(8)]
EVALS = [f'tgeval{i}' for i in range(8)]
UDS_DIR = Path('/root/tgv')      # vLLM listens ONLY on a root-only Unix socket
UDS = UDS_DIR / 'vllm.sock'
DIVERSITY_REPLICATES = 3         # 9.1 seed diversity: r2..r4 on one pilot template, paraphrase 1
RESUME_SHA256 = ''               # build --define: expected hash of a previous results_sealed.tar.gz
R = {'started': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'phases': {}}
HF_EXPECTED = {  # google/gemma-4-31B-it-qat-w4a16-ct @ 52f3f65bc7a02d555763bc923bd1d9094898219d
    'model.safetensors': ('sha256', '1b9b1d622a93f02c0d33f98e502f233b5d707443af6ddc464ed0bf5498506c20'),
    'tokenizer.json': ('sha256', 'cc8d3a0ce36466ccc1278bf987df5f71db1719b9ca6b4118264f45cb627bfe0f'),
    'config.json': ('git', 'e8beda78f4e93f78a5d9d8f2b78cd9bc272d35e5'),
    'chat_template.jinja': ('git', '4741bf6e4132ba23a5537f9d6e74e9a6d613d7cd'),
    'generation_config.json': ('git', 'f6bc6f4146a610a3881015c90d36a78beb1333bb'),
    'tokenizer_config.json': ('git', 'b22e2c5c05597a7e8c0cb1cebdb7d45570772005'),
}


def save():
    OUT.write_text(json.dumps(R, indent=1, default=str))


def phase(name):
    def deco(fn):
        def run(*a, **k):
            t0 = time.time()
            try:
                res = fn(*a, **k)
                R['phases'][name] = {'ok': True, 'seconds': round(time.time() - t0, 1), **(res or {})}
            except Exception as exc:
                R['phases'][name] = {'ok': False, 'seconds': round(time.time() - t0, 1),
                                     'error': f'{type(exc).__name__}: {exc}',
                                     'trace': traceback.format_exc()[-3000:]}
            save()
            print(f'== {name}: ', json.dumps(R['phases'][name], default=str)[:1500], flush=True)
            return R['phases'][name]
        return run
    return deco


def sh(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout.strip()


# ------------------------------------------------------------------ 0 guard
@phase('0_gpu_guard')
def gpu_guard():
    smi = sh('nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader')
    gpus = [l for l in smi.splitlines() if l.strip()]
    info = {'gpus': gpus, 'topo': sh('nvidia-smi topo -m'), 'python': sys.version,
            'cpus': os.cpu_count(), 'ram': sh('free -g | head -2')}
    if len(gpus) != 4 or not all('L4' in g for g in gpus):
        info['abort'] = True
        R['phases']['0_gpu_guard'] = {'ok': False, **info}
        save()
        raise SystemExit(f'GPU mismatch, aborting: {gpus}')
    return info


# ------------------------------------------------------------------ 1 wheels
@phase('1_wheels')
def install_wheels():
    whl_dir = Path(glob.glob('/kaggle/input/**/gemma-4-developer-agent-wheelhouse', recursive=True)[0])
    for pth in glob.glob('/usr/local/lib/python*/*-packages/*cutlass*.pth'):
        try:
            os.unlink(pth)
        except OSError:
            pass
    tmp = Path('/tmp/wheelhouse'); tmp.mkdir(exist_ok=True)
    for w in whl_dir.glob('*.whl'):
        if 'cutlass' in w.name.lower():
            continue
        name = w.name.replace('cu128', '+cu128') if ('cu128' in w.name and '+' not in w.name) else w.name
        if not (tmp / name).exists():
            os.symlink(w, tmp / name)
    wheels = sorted(str(w) for w in tmp.glob('*.whl'))
    r = subprocess.run([sys.executable, '-m', 'pip', 'install', '--no-deps', '--force-reinstall',
                        *wheels], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError('pip failed:\n' + (r.stdout + r.stderr)[-4000:])
    ver = sh(f'{sys.executable} -c "import vllm,torch,transformers;print(vllm.__version__,torch.__version__,transformers.__version__)"')
    return {'wheelhouse': str(whl_dir), 'n_wheels': len(wheels), 'vllm_torch_transformers': ver}


# ------------------------------------------------------------------ server
MODEL = None
OFFICIAL_FLAGS = ['--max-model-len', '32768', '--gpu-memory-utilization', '0.90',
                  '--enable-auto-tool-choice', '--tool-call-parser', 'gemma4',
                  '--reasoning-parser', 'gemma4', '--dtype', 'bfloat16',
                  '--served-model-name', 'gemma']


KAGGLE_MODEL = None
OVERLAY_FILES = ('chat_template.jinja', 'tokenizer_config.json')


def model_path():
    """Kaggle weights + the two small files of HF revision 52f3f65 (Kaggle v2 ships the
    older release revision ca9d525 for them; weights are identical, see phase 7)."""
    global KAGGLE_MODEL
    c = glob.glob('/kaggle/input/**/gemma-4-31b-it-qat-w4a16-ct/2', recursive=True)
    if not c:
        raise FileNotFoundError('31B QAT model input not attached')
    KAGGLE_MODEL = Path(c[0])
    dest = Path('/kaggle/working/model_52f3f65')
    dest.mkdir(parents=True, exist_ok=True)
    overlay = code_dir() / 'notebooks' / 'model_overlay'
    for f in KAGGLE_MODEL.iterdir():
        if f.name not in OVERLAY_FILES and not (dest / f.name).exists():
            os.symlink(f, dest / f.name)
    for name in OVERLAY_FILES:
        shutil.copyfile(overlay / name, dest / name)
    return dest


SERVED = {}   # port -> served model id


def uds_request(method, path, body=None, timeout=10):
    import http.client, socket

    class Conn(http.client.HTTPConnection):
        def connect(self):
            so = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            so.settimeout(timeout)
            so.connect(str(UDS))
            self.sock = so
    c = Conn('localhost', timeout=timeout)
    try:
        c.request(method, path, body=json.dumps(body).encode() if body is not None else None,
                  headers={'Content-Type': 'application/json'})
        r = c.getresponse()
        return r.status, r.read()
    finally:
        c.close()


def start_server(tp, gpus, port, tag, extra=()):
    """Official adk_submission.VllmServer with the getting-started notebook's VllmConfig."""
    os.environ.update(CUDA_VISIBLE_DEVICES=gpus, VLLM_NO_USAGE_STATS='1',
                      VLLM_WORKER_MULTIPROC_METHOD='spawn', TRANSFORMERS_OFFLINE='1',
                      VLLM_ENGINE_READY_TIMEOUT_S='1200',
                      VLLM_MEMORY_PROFILER_ESTIMATE_CUDAGRAPHS='1', NCCL_DEBUG='WARN',
                      PYTORCH_CUDA_ALLOC_CONF='expandable_segments:True')
    from adk_submission import VllmConfig, VllmServer
    use_uds = '--uds' in extra

    class Server(VllmServer):
        def is_healthy(self):
            if not use_uds:
                return super().is_healthy()
            try:
                return uds_request('GET', '/health', timeout=2)[0] == 200
            except Exception:
                return False
    cfg = VllmConfig(model=str(MODEL), port=port, host='127.0.0.1', tool_call_parser='gemma4',
                     reasoning_parser='gemma4', max_model_len=32768, dtype='bfloat16',
                     gpu_memory_utilization=0.90, enable_auto_tool_choice=True,
                     enable_lora=False, scheduler_reserve_full_isl=False,
                     tensor_parallel_size=tp, startup_timeout=60 * 20, extra_args=tuple(extra))
    t0 = time.time()
    srv = Server(cfg)
    box = {}

    def run():
        try:
            srv.start()
            box['ok'] = True
        except Exception as e:
            box['err'] = e
    th = threading.Thread(target=run, daemon=True)
    th.start()
    dead = ('EngineCore failed to start', 'CUDA out of memory')
    while th.is_alive():
        th.join(10)
        log = getattr(srv, 'log_path', None)
        if log and Path(log).exists():
            shutil.copyfile(log, f'/kaggle/working/vllm_{tag}.log')
            text = Path(log).read_text(errors='replace')
            if any(d in text for d in dead):
                try:
                    srv.stop()
                except Exception:
                    pass
                time.sleep(15)
                raise RuntimeError('engine failed: ' + text[-1500:])
    if 'err' in box:
        raise box['err']
    if use_uds:
        st, raw = uds_request('GET', '/v1/models')
        SERVED[port] = json.loads(raw)['data'][0]['id']
    else:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/v1/models', timeout=10) as r:
            SERVED[port] = json.loads(r.read())['data'][0]['id']
    return srv, round(time.time() - t0, 1), list(extra)


def kv_info(tag):
    text = Path(f'/kaggle/working/vllm_{tag}.log').read_text(errors='replace')
    keys = ('KV cache', 'Maximum concurrency', 'Loading weights took', 'Model loading took',
            'graph capturing', 'Available KV')
    return [l.strip()[-220:] for l in text.splitlines() if any(k in l for k in keys)][:12]


def chat(port, body, timeout=900):
    req = urllib.request.Request(f'http://127.0.0.1:{port}/v1/chat/completions',
                                 data=json.dumps({'model': SERVED.get(port, 'gemma'), **body}).encode(),
                                 headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {'http_error': e.code, 'body': e.read().decode(errors='replace')[:1500]}


SAMPLING = {'temperature': 1.0, 'top_p': 0.95, 'top_k': 64}
TOOLS = [{'type': 'function', 'function': {
    'name': 'read_file', 'description': 'Read a file.',
    'parameters': {'type': 'object', 'properties': {'filepath': {'type': 'string'}},
                   'required': ['filepath']}}}]


# ------------------------------------------------------------------ 3 behaviour
def checks(port):
    out = {}
    q = [{'role': 'user', 'content': 'What is 17*23? Answer with the number only.'}]
    for label, extra in (('thinking_on_budget', {'chat_template_kwargs': {'enable_thinking': True},
                                                 'thinking_token_budget': 4096}),
                         ('thinking_on', {'chat_template_kwargs': {'enable_thinking': True}}),
                         ('thinking_off', {'chat_template_kwargs': {'enable_thinking': False}})):
        r = chat(port, {'messages': q, 'max_tokens': 4096, 'seed': 1, **SAMPLING, **extra})
        if 'http_error' in r:
            out[label] = r
            continue
        m = r['choices'][0]['message']
        rc = m.get('reasoning_content') or m.get('reasoning')
        out[label] = {'content': (m.get('content') or '')[:200], 'has_reasoning': bool(rc),
                      'reasoning_chars': len(rc or ''), 'usage': r.get('usage'),
                      'finish': r['choices'][0].get('finish_reason')}
    r = chat(port, {'messages': [{'role': 'user', 'content': 'Read the file src/app.py using the tool.'}],
                    'tools': TOOLS, 'tool_choice': 'auto', 'max_tokens': 4096, 'seed': 1,
                    'chat_template_kwargs': {'enable_thinking': True}, **SAMPLING})
    if 'http_error' in r:
        out['tool_call'] = r
    else:
        m = r['choices'][0]['message']
        out['tool_call'] = {'tool_calls': m.get('tool_calls'), 'content': (m.get('content') or '')[:300],
                            'raw_tag_in_content': '<|tool_call>' in (m.get('content') or '')}
    # Same seed twice: is sampling reproducible on this engine? (recorded, not assumed)
    a = chat(port, {'messages': q, 'max_tokens': 256, 'seed': 7, **SAMPLING,
                    'chat_template_kwargs': {'enable_thinking': False}})
    b = chat(port, {'messages': q, 'max_tokens': 256, 'seed': 7, **SAMPLING,
                    'chat_template_kwargs': {'enable_thinking': False}})
    try:
        out['same_seed_identical'] = (a['choices'][0]['message']['content'] ==
                                      b['choices'][0]['message']['content'])
    except Exception:
        out['same_seed_identical'] = None
    return out


# ------------------------------------------------------------------ code bundle
# notebooks/build_kernel.py replaces the marker below with CODE_COMMIT and CODE_B64.
# @@CODE_BUNDLE@@


def code_dir():
    import base64, io, tarfile
    dest = Path('/kaggle/working/code')
    if not (dest / 'harness').exists():
        dest.mkdir(parents=True, exist_ok=True)
        with tarfile.open(fileobj=io.BytesIO(base64.b64decode(CODE_B64)), mode='r:gz') as t:
            t.extractall(dest)
        R['code_commit'] = CODE_COMMIT
    return dest


# ------------------------------------------------------------------ 4 throughput
def long_prompt():
    text = (code_dir() / 'harness' / 'loop.py').read_text()[:22000]
    return [{'role': 'user', 'content': 'Review this module and list three risky functions with '
             'a one-line reason each.\n\n```python\n' + text + '\n```'}]


def throughput(ports):
    msgs = long_prompt()
    res = {}
    for conc in (1, 4, 8, 16):
        n = max(4, conc * 2)
        body = {'messages': msgs, 'max_tokens': 1024, 'seed': 3, **SAMPLING,
                'chat_template_kwargs': {'enable_thinking': True}}
        t0 = time.time()
        with ThreadPoolExecutor(conc) as ex:
            outs = list(ex.map(lambda i: (time.time(), chat(ports[i % len(ports)], body),
                                          time.time()), range(n)))
        wall = time.time() - t0
        ok = [o for o in outs if 'choices' in o[1]]
        comp = sum(o[1]['usage']['completion_tokens'] for o in ok)
        prompt_toks = ok[0][1]['usage']['prompt_tokens'] if ok else None
        res[str(conc)] = {'requests': n, 'ok': len(ok), 'wall_s': round(wall, 1),
                          'completion_tok_per_s': round(comp / wall, 1),
                          'mean_latency_s': round(sum(o[2] - o[0] for o in ok) / max(1, len(ok)), 1),
                          'prompt_tokens': prompt_toks}
        save()
    return res


# ------------------------------------------------------------------ 5 harness episode
def episode(port):
    code = code_dir()
    sys.path.insert(0, str(code))
    from harness import contract as C
    from harness.loop import OpenAICompatClient, run_episode
    from harness.workspace import Workspace
    from bank.render import load, render, task_for
    t, meta = load(code / 'tests' / 'fixtures' / 'tpl_m1')
    base = Path('/kaggle/working/episode')
    if base.exists():
        shutil.rmtree(base)
    ws_dir = render(t, 'N', base / 'ws')
    ws = Workspace(ws_dir, base / 'tmp')
    ws.init_baseline()
    client = OpenAICompatClient(f'http://127.0.0.1:{port}/v1', SERVED[port], timeout=900)
    s = run_episode(task_for(meta), ws, client, C.Budget(tool_calls=30, time_minutes=15),
                    base / 'episode_log.jsonl',
                    {**SAMPLING, 'seed': 11, 'enable_thinking': True})
    s['patch'] = s['patch'][:2000]
    return s


# ------------------------------------------------------------------ 6 WP7 (provisional)
def wp7(port):
    """Manipulation check on the pilot templates. PROVISIONAL: recorded for planning;
    the official WP7 run happens once the serving configuration is decided."""
    code = code_dir()
    sys.path.insert(0, str(code))
    from bank import manipulation_check as mc
    from harness.loop import OpenAICompatClient
    client = OpenAICompatClient(f'http://127.0.0.1:{port}/v1', SERVED[port], timeout=900)
    log = Path('/kaggle/working/wp7_provisional.jsonl')
    out = []
    for t in sorted((code / 'bank' / 'templates').iterdir()):
        out.append(mc.check(t, client, {**SAMPLING, 'enable_thinking': True}, log))
        save()
    return out


# ------------------------------------------------------------------ 7 hashes
def git_blob_sha1(path):
    data = Path(path).read_bytes()
    return hashlib.sha1(b'blob %d\0' % len(data) + data).hexdigest()


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 24), b''):
            h.update(chunk)
    return h.hexdigest()


@phase('7_model_hashes')
def model_hashes():
    out = {'files': sorted(p.name for p in MODEL.iterdir()), 'served_dir': str(MODEL),
           'kaggle_dir': str(KAGGLE_MODEL)}
    for name, (kind, expected) in HF_EXPECTED.items():
        p = MODEL / name
        if not p.exists():
            out[name] = 'missing'
            continue
        got = sha256(p) if kind == 'sha256' else git_blob_sha1(p)
        out[name] = {'match': got == expected, 'got': got}
    out['all_match'] = all(isinstance(v, dict) and v['match'] for k, v in out.items()
                           if k in HF_EXPECTED)
    return out


def stop(procs):
    for p in procs:
        try:
            p.stop()
        except Exception:
            pass
    SERVED.clear()
    time.sleep(15)


def run_config(tag, layout):
    """layout: list of (tp, gpus, port)."""
    procs = []

    @phase(f'2_server_{tag}')
    def up():
        loads = []
        threads, errs = [], []

        used_extra = {}
        for tp, gpus, port in layout:   # sequential: os.environ carries CUDA_VISIBLE_DEVICES
            last = None
            for extra in ((), ('--max-num-seqs', '32')):
                try:
                    p, secs, ex = start_server(tp, gpus, port, f'{tag}_{port}', extra)
                    procs.append(p); loads.append(secs); used_extra[port] = ex
                    break
                except Exception as e:
                    last = f'{type(e).__name__}: {e}'
                    errs.append({'port': port, 'extra': list(extra), 'error': last[-1500:],
                                 'log_tail': kv_info(f'{tag}_{port}')})
            else:
                raise RuntimeError(json.dumps(errs)[-4000:])
        os.environ['CUDA_VISIBLE_DEVICES'] = '0,1,2,3'
        return {'load_seconds': loads, 'extra_args': used_extra, 'failed_attempts': errs,
                'served': SERVED, 'nvidia_smi': sh('nvidia-smi --query-gpu=memory.used --format=csv'),
                'kv': {port: kv_info(f'{tag}_{port}') for _, _, port in layout}}
    if not up()['ok']:
        stop(procs)
        return
    ports = [p for _, _, p in layout]
    phase(f'3_checks_{tag}')(lambda: {'checks': checks(ports[0])})()
    phase(f'4_throughput_{tag}')(lambda: {'by_concurrency': throughput(ports)})()
    if tag == 'tp4':
        phase('5_episode_tp4')(lambda: {'summary': episode(ports[0])})()
        phase('6_wp7_provisional')(lambda: {'results': wp7(ports[0])})()
    stop(procs)


ISO = {}


def as_user(u, cmd):
    return sh(f'setpriv --reuid={u} --regid={u} --clear-groups --no-new-privs -- '
              f'bash -c {json.dumps(cmd)} >/dev/null 2>&1; echo $?')


@phase('8_isolation')
def isolation(code):
    """Unprivileged agent/evaluator uid per slot; /kaggle (kernel source with the bundled bank,
    inputs, working dir) closed to them; bank root-only; vLLM on a root-only Unix socket.
    Every denial is CHECKED and the kernel aborts if any is missing (docs/decisions.md D5)."""
    out = {}
    for u in AGENTS + EVALS:
        out[f'useradd_{u}'] = sh(f'id {u} >/dev/null 2>&1 || useradd -M -s /bin/bash {u}; id -u {u}')
    sh(f'chmod -R go-rwx {code}')                      # harness, bank, oracles: root only
    sh('chmod 0700 /kaggle')                            # /kaggle/src holds the code bundle
    sh('chmod 0700 /root')
    out['chmod_scratch'] = sh('chmod 1733 /tmp /var/tmp /dev/shm && stat -c "%a" /tmp /var/tmp /dev/shm')
    if out['chmod_scratch'].split() != ['1733'] * 3:      # shared scratch: not listable
        raise RuntimeError(f"scratch dirs not locked: {out['chmod_scratch']}")
    UDS_DIR.mkdir(parents=True, exist_ok=True)
    UDS_DIR.chmod(0o700)
    work = Path('/tmp/wk'); work.mkdir(exist_ok=True); work.chmod(0o711)
    oracle = next((code / 'bank' / 'templates').glob('*/oracle/oracle.py'))
    probes = {'kernel_src_ls': 'ls /kaggle/src', 'kernel_src_cat': 'cat /kaggle/src/script.py',
              'inputs_ls': 'ls /kaggle/input', 'working_ls': 'ls /kaggle/working',
              'oracle_cat': f'cat {oracle}', 'bank_ls': f'ls {code}/bank/templates',
              'harness_cat': f'cat {code}/harness/loop.py', 'root_ls': 'ls /root',
              'uds_dir_ls': f'ls {UDS_DIR}', 'tmp_ls': 'ls /tmp', 'wk_ls': 'ls /tmp/wk',
              'var_tmp_ls': 'ls /var/tmp', 'shm_ls': 'ls /dev/shm'}
    failures = []
    for u in (AGENTS[0], EVALS[0], AGENTS[-1], EVALS[-1]):
        for k, c in probes.items():
            rc = as_user(u, c)
            out[f'{u}_{k}_rc'] = rc
            if rc == '0':
                failures.append(f'{u}:{k}')
    out['python_ok_as_agent'] = as_user(AGENTS[0], f'{sys.executable} -c "import pytest"')
    if out['python_ok_as_agent'] != '0':
        failures.append('agent cannot run python/pytest')
    out['failures'] = failures
    ISO.update(out)
    if failures:
        raise RuntimeError(f'isolation checks failed: {failures}')
    return out


@phase('8b_server_unreachable')
def server_unreachable():
    """After vLLM is up: no agent/evaluator uid can reach it (socket or TCP)."""
    probe_uds = (f"{sys.executable} -c \"import socket;s=socket.socket(socket.AF_UNIX);"
                 f"s.connect('{UDS}')\"")
    probe_tcp = (f"{sys.executable} -c \"import socket,sys;s=socket.socket();s.settimeout(2);"
                 f"sys.exit(0 if s.connect_ex(('127.0.0.1',8000))==0 else 1)\"")
    out, failures = {}, []
    for u in (AGENTS[0], EVALS[0]):
        out[f'{u}_uds_rc'] = as_user(u, probe_uds)
        out[f'{u}_tcp8000_rc'] = as_user(u, probe_tcp)
        if out[f'{u}_uds_rc'] == '0' or out[f'{u}_tcp8000_rc'] == '0':
            failures.append(u)
    out['root_health'] = uds_request('GET', '/health')[0]
    # engine-internal listeners (NCCL/TCPStore, ZMQ): recorded with their reachability
    ports = set()
    for f in ('/proc/net/tcp', '/proc/net/tcp6'):
        try:
            for line in Path(f).read_text().splitlines()[1:]:
                parts = line.split()
                if parts[3] == '0A':                   # LISTEN
                    ports.add(int(parts[1].rsplit(':', 1)[1], 16))
        except Exception:
            pass
    hosts = ['127.0.0.1'] + [h for h in sh('hostname -I').split() if ':' not in h]
    reach = {}
    for port in sorted(ports):
        for host in hosts:
            probe = (f"{sys.executable} -c \"import socket,sys;s=socket.socket();s.settimeout(2);"
                     f"sys.exit(0 if s.connect_ex(('{host}',{port}))==0 else 1)\"")
            if as_user(AGENTS[0], probe) == '0':
                reach.setdefault(port, []).append(host)
    out['tcp_listeners'] = len(ports)
    out['tcp_reachable_by_agent'] = reach            # expected: the TCPStore rendezvous only
    # Unix sockets with a path (vLLM engine ZMQ ipc carries serialized objects): an agent
    # that could connect would reach root code paths -> abort. Abstract ones are recorded.
    paths, abstract = set(), 0
    for line in Path('/proc/net/unix').read_text().splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 8:
            if parts[7].startswith('@'):
                abstract += 1
            else:
                paths.add(parts[7])
    connectable = []
    for path in sorted(paths):
        probe = (f"{sys.executable} -c \"import socket;s=socket.socket(socket.AF_UNIX);"
                 f"s.settimeout(2);s.connect('{path}')\"")
        if as_user(AGENTS[0], probe) == '0':
            connectable.append(path)
    out['unix_path_sockets'] = len(paths)
    out['unix_path_sockets_connectable_by_agent'] = connectable
    out['unix_abstract_sockets'] = abstract
    if connectable:
        failures.append(f'unix sockets reachable: {connectable}')
    if failures or out['root_health'] != 200:
        raise RuntimeError(f'server reachable by {failures} or unhealthy: {out}')
    return out


def runner_cmd(code, mode, out_dir, extra):
    env_id = ('kaggle-L4x4|' + sh("nvidia-smi --query-gpu=name --format=csv,noheader | sort | uniq -c | tr -s ' '")
              + '|img:37c64f7d|vllm0.19.1|tp4|model:52f3f65-overlay')
    args = ['--split', 'pilot', '--out', str(out_dir), '--work', '/tmp/wk',
            '--base-url', f'unix:{UDS}', '--model', SERVED[8000],
            '--model-revision', R['verified_revision'],
            '--run-as', ','.join(AGENTS), '--eval-user', ','.join(EVALS),
            '--concurrency', str(len(AGENTS)), '--environment-id', env_id,
            '--code-commit', CODE_COMMIT,
            '--stop-at', str(KERNEL_T0 + SESSION_LIMIT_S - STOP_MARGIN_S), *extra]
    # arguments go through a root-only file: the process list is visible to every uid
    argf = UDS_DIR / f'args_{out_dir.name}'
    argf.write_text('\n'.join(args) + '\n')
    return [sys.executable, str(code / 'runner' / 'runner.py'), f'@{argf}']


def blind_summary(out_dir):
    """Pooled, framing-free numbers only (9.2)."""
    import csv as _csv
    csvp = out_dir / 'runs.csv'
    if not csvp.exists():
        return {}
    rows = list(_csv.DictReader(open(csvp)))
    res = {'n_rows': len(rows),
           'status_counts': {s: sum(1 for x in rows if x['status'] == s) for s in {x['status'] for x in rows}},
           'termination_counts': {s: sum(1 for x in rows if x['termination'] == s) for s in {x['termination'] for x in rows}}}
    el = [float(x['elapsed_seconds']) for x in rows if x['elapsed_seconds']]
    res['mean_elapsed_s'] = round(sum(el) / max(1, len(el)), 1)
    res['max_elapsed_s'] = round(max(el or [0]), 1)
    return res


CHECKPOINT_EVERY_S = 15 * 60


SEALED = Path('/kaggle/working/results_sealed.tar.gz')
SEAL_LOCK = threading.Lock()     # one snapshot/seal at a time (periodic and final)


def snapshot_and_seal():
    """Consistent snapshot, then an atomic durable replace of the sealed archive (the previous
    archive stays valid until the new one is complete).
    Consistency: every event in attempts.jsonl refers to files written BEFORE the event, so
    each block's attempts.jsonl is copied FIRST and its other files afterwards: every logged
    event finds its files in the snapshot (later extra files are harmless checkpoints)."""
    with SEAL_LOCK:
        return _snapshot_and_seal()


def _snapshot_and_seal():
    import tarfile, tempfile
    res_dir = Path('/kaggle/working/results')
    stage = Path(tempfile.mkdtemp(prefix='snap_', dir='/root/tgv'))
    fd, tmp_name = tempfile.mkstemp(prefix='.sealed_', suffix='.tmp', dir='/kaggle/working')
    tmp = Path(tmp_name)
    try:
        for block in sorted(d for d in res_dir.iterdir() if d.is_dir()):
            dst = stage / block.name
            dst.mkdir()
            if (block / 'attempts.jsonl').exists():
                shutil.copy2(block / 'attempts.jsonl', dst / 'attempts.jsonl')
            for item in sorted(block.iterdir()):
                if item.name == 'attempts.jsonl':
                    continue
                if item.is_dir():
                    shutil.copytree(item, dst / item.name, ignore=shutil.ignore_patterns('*.tmp'))
                elif not item.name.endswith('.tmp'):
                    shutil.copy2(item, dst / item.name)
        with os.fdopen(fd, 'wb') as raw:
            fd = None
            with tarfile.open(fileobj=raw, mode='w:gz') as t:
                t.add(stage, arcname='results')
            raw.flush()
            os.fsync(raw.fileno())
        os.replace(tmp, SEALED)
        dfd = os.open('/kaggle/working', os.O_RDONLY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
        return sha256(SEALED)
    finally:
        if fd is not None:
            os.close(fd)
        tmp.unlink(missing_ok=True)          # no-op after a successful replace
        shutil.rmtree(stage, ignore_errors=True)


def checkpoint():
    R['last_checkpoint'] = {'utc': time.strftime('%H:%M:%S', time.gmtime()),
                            'sha256': snapshot_and_seal()}
    save()


def run_block(code, mode, name, extra):
    out_dir = Path('/kaggle/working/results') / name
    cmd = runner_cmd(code, mode, out_dir, extra)
    t0 = time.time()
    done = threading.Event()

    def loop():
        while not done.wait(CHECKPOINT_EVERY_S):
            try:
                checkpoint()
            except Exception as exc:
                R['checkpoint_error'] = f'{type(exc).__name__}: {exc}'
    th = threading.Thread(target=loop, daemon=True)
    th.start()
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(code))
    finally:
        done.set()
        th.join()        # a checkpoint in progress always finishes before anything else
    res = {'rc': r.returncode, 'wall_seconds': round(time.time() - t0, 1),
           'stdout_tail': r.stdout[-1500:], 'stderr_tail': r.stderr[-3000:]}
    R.setdefault('blocks', {})[name] = res
    if r.returncode != 0:
        raise RuntimeError(f'runner block {name} failed rc={r.returncode}: {r.stderr[-1500:]}')
    try:
        meta = json.loads((out_dir / 'session_summary.json').read_text())
        res['session'] = {k: meta.get(k) for k in ('scheduled', 'completed', 'ran_now',
                                                   'skipped_by_deadline', 'needs_adjudication',
                                                   'wall_seconds_this_session', 'concurrency')}
    except Exception:
        pass
    res.update(blind_summary(out_dir))
    try:
        res['infra_access_scan'] = scan_logs(name)
    except Exception as exc:
        res['infra_access_scan'] = f'{type(exc).__name__}: {exc}'

    return res


SCAN = {'proc': r'/proc/', 'localhost': r'127\.0\.0\.1|localhost|0\.0\.0\.0',
        'socket': r'\bsocket\b|\bnc\b|netcat|curl|wget|/dev/tcp', 'kaggle': r'/kaggle',
        'root_dirs': r'/root|/tgv', 'process_list': r'\bps\b|pgrep|/proc/\d', 'base64': r'base64',
        'other_tmp': r'/tmp/wk|/var/tmp|/dev/shm'}


def scan_logs(name):
    """Pooled count of runs whose agent tool calls touch the infrastructure (declared risk,
    measured). Reads the controller logs; reports counts only (no framing)."""
    import re
    logs = Path('/kaggle/working/results') / name / 'logs'
    hits = {k: 0 for k in SCAN}
    runs = {}
    for f in logs.glob('*.jsonl'):
        rid = f.name.split('.t')[0]
        text = []
        for line in f.read_text(errors='replace').splitlines():
            try:
                ev = json.loads(line)
            except Exception:
                continue
            if ev.get('event') == 'tool':
                text.append(json.dumps(ev.get('arguments')))
        runs.setdefault(rid, []).append('\n'.join(text))
    for rid, chunks in runs.items():
        blob = '\n'.join(chunks)
        for k, pat in SCAN.items():
            if re.search(pat, blob):
                hits[k] += 1
    return {'runs_scanned': len(runs), 'runs_matching': hits}


def pilot_gates(code):
    """twinguard_analysis.py --pilot: pooled rates and gates only (blind by construction).
    Only on a complete pilot with no run awaiting blind adjudication."""
    out_dir = Path('/kaggle/working/results') / 'pilot'
    meta = json.loads((out_dir / 'session_summary.json').read_text())
    if meta['completed'] != meta['scheduled'] or meta['needs_adjudication']:
        return {'deferred': True, 'completed': meta['completed'], 'scheduled': meta['scheduled'],
                'needs_adjudication': meta['needs_adjudication']}
    r = subprocess.run([sys.executable, str(code / 'twinguard' / 'twinguard_analysis.py'),
                        str(out_dir / 'runs.csv'), '--pilot', '--replicates', '1'],
                       capture_output=True, text=True, cwd=str(code))
    Path('/kaggle/working/pilot_gates.txt').write_text(r.stdout + '\n' + r.stderr[-3000:])
    if r.returncode != 0:
        raise RuntimeError(f'pilot analysis failed rc={r.returncode}: {r.stderr[-1500:]}')
    return {'rc': r.returncode, 'report': r.stdout[-4000:]}


def diversity_block(code):
    """9.1: extra seeds (r2..r4) on one pilot template, paraphrase 1, all framings. Reported
    pooled: mean number of distinct patches among the 4 seeds of a cell."""
    import csv as _csv
    tid = sorted(r['template_id'] for r in _csv.DictReader(open(code / 'bank' / 'spec_matrix.csv'))
                 if r['split'] == 'pilot')[0]
    res = run_block(code, 'pilot', 'pilot_diversity',
                    ['--only-template', tid, '--only-paraphrase', '1', '--first-replicate', '2',
                     '--replicates', str(DIVERSITY_REPLICATES)])
    pats = {}
    for name in ('pilot', 'pilot_diversity'):
        for pf in (Path('/kaggle/working/results') / name / 'patches').glob(f'*{tid}*__p1__*.patch'):
            cell = pf.name.split('__')[2]            # framing: used ONLY as a grouping key
            pats.setdefault(cell, []).append(hashlib.sha256(pf.read_bytes()).hexdigest())
    complete = [v for v in pats.values() if len(v) == 1 + DIVERSITY_REPLICATES]
    ok = len(pats) == 3 and len(complete) == 3
    res['diversity'] = {'complete': ok, 'cells': len(pats),
                        'seeds_per_cell': sorted(len(v) for v in pats.values()),
                        'mean_distinct_patches': (round(sum(len(set(v)) for v in complete) / 3, 2)
                                                  if ok else None)}
    return res


def seal_results():
    """Raw results (framings, logs) go into one archive whose hash is reported; only pooled
    numbers and the blind CSV are left in the open (9.2)."""
    import csv as _csv, tarfile
    res_dir = Path('/kaggle/working/results')
    for name in ('pilot', 'pilot_diversity', 'runner_smoke'):
        csvp = res_dir / name / 'runs.csv'
        summ = res_dir / name / 'session_summary.json'
        if csvp.exists() and summ.exists():
            meta = json.loads(summ.read_text())
            if meta['completed'] != meta['scheduled']:
                R.setdefault('blind_csv_withheld', []).append(name)   # incomplete: linkable
                continue
            rows = list(_csv.DictReader(open(csvp)))
            cols = [c for c in rows[0].keys() if c not in ('framing', 'run_id')] if rows else []
            with open(f'/kaggle/working/runs_blind_{name}.csv', 'w', newline='') as f:
                w = _csv.DictWriter(f, fieldnames=['row'] + [c for c in cols if c != 'seed'])
                w.writeheader()
                import secrets
                secrets.SystemRandom().shuffle(rows)   # private, unrecorded permutation
                for i, x in enumerate(rows):
                    w.writerow({'row': i, **{c: x[c] for c in cols if c != 'seed'}})
    digest = snapshot_and_seal()          # nothing is writing any more: final and complete
    shutil.rmtree(res_dir)
    return {'sealed': str(SEALED), 'sha256': digest, 'bytes': SEALED.stat().st_size}


def restore_previous():
    """Resume: a previous version's sealed results attached as a kernel source."""
    prev = glob.glob('/kaggle/input/**/results_sealed.tar.gz', recursive=True)
    if not RESUME_SHA256:
        if prev:
            raise RuntimeError(f'sealed results attached but no RESUME_SHA256 defined: {prev}')
        return {'resumed_from': None}
    match = [x for x in prev if sha256(x) == RESUME_SHA256]
    if len(match) != 1:
        raise RuntimeError(f'expected exactly one sealed archive with sha256 {RESUME_SHA256}: {prev}')
    import tarfile
    with tarfile.open(match[0]) as t:
        t.extractall('/kaggle/working')
    return {'resumed_from': match[0], 'sha256': RESUME_SHA256}


def smoke_block(code):
    spec = UDS_DIR / 'fixture_spec.csv'
    fb = UDS_DIR / 'fixture_bank'
    fb.mkdir(exist_ok=True)
    dst = fb / 'FIXTURE.m1_toy'
    if not dst.exists():
        shutil.copytree(code / 'tests' / 'fixtures' / 'tpl_m1', dst)
        m = json.loads((dst / 'template.json').read_text())
        m['issue_paraphrases'] = [m['problem_statement']] * 4
        (dst / 'template.json').write_text(json.dumps(m))
    spec.write_text('template_id,split,family,mechanism\nFIXTURE.m1_toy,pilot,logistics,M1\n')
    return run_block(code, 'runner_smoke', 'runner_smoke',
                     ['--bank', str(fb), '--spec', str(spec), '--limit', '6', '--replicates', '1'])


if __name__ == '__main__':
    gpu_guard()
    install_wheels()
    procs = []
    try:
        code = code_dir()
        MODEL = model_path()
        R['model_path'] = str(MODEL)
        h = model_hashes()
        if h['ok'] and h.get('all_match'):
            R['verified_revision'] = '52f3f65bc7a02d555763bc923bd1d9094898219d'
        else:
            raise SystemExit('served model files do not match HF 52f3f65: refusing to run')
        Path('/kaggle/working/results').mkdir(parents=True, exist_ok=True)
        if not phase('8a_restore')(restore_previous)()['ok']:
            raise SystemExit('resume archive check failed: refusing to run')
        if not isolation(code)['ok']:
            raise SystemExit('isolation checks failed: refusing to run')

        @phase('2_server_tp4')
        def up():
            p, secs, ex = start_server(4, '0,1,2,3', 8000, 'tp4_8000', ('--uds', str(UDS)))
            procs.append(p)
            return {'load_seconds': secs, 'served': dict(SERVED), 'extra_args': ex}
        if up()['ok'] and server_unreachable()['ok']:
            if MODE == 'pilot':
                main = phase('9_runner_pilot')(lambda: run_block(code, 'pilot', 'pilot', ['--replicates', '1']))()
                if main['ok']:
                    phase('9b_pilot_gates')(lambda: pilot_gates(code))()
                if time.time() < KERNEL_T0 + SESSION_LIMIT_S - STOP_MARGIN_S:
                    phase('9c_seed_diversity')(lambda: diversity_block(code))()
            else:
                phase('9_runner_smoke')(lambda: smoke_block(code))()
    finally:
        stop(procs)
        try:
            phase('10_seal')(seal_results)()
        except Exception:
            pass
        sh('chmod 0755 /kaggle')
        shutil.rmtree('/kaggle/working/code', ignore_errors=True)
        shutil.rmtree('/kaggle/working/model_52f3f65', ignore_errors=True)
        R['finished'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        save()
        print('DONE', flush=True)
