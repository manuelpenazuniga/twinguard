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
MODE = 'runner_smoke'   # 'runner_smoke' (toy fixture, 6 runs) or 'pilot' (72 runs); set at build time
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


def start_server(tp, gpus, port, tag, extra=()):
    """Official adk_submission.VllmServer with the getting-started notebook's VllmConfig."""
    os.environ.update(CUDA_VISIBLE_DEVICES=gpus, VLLM_NO_USAGE_STATS='1',
                      VLLM_WORKER_MULTIPROC_METHOD='spawn', TRANSFORMERS_OFFLINE='1',
                      VLLM_ENGINE_READY_TIMEOUT_S='1200',
                      VLLM_MEMORY_PROFILER_ESTIMATE_CUDAGRAPHS='1', NCCL_DEBUG='WARN',
                      PYTORCH_CUDA_ALLOC_CONF='expandable_segments:True')
    from adk_submission import VllmConfig, VllmServer
    cfg = VllmConfig(model=str(MODEL), port=port, host='127.0.0.1', tool_call_parser='gemma4',
                     reasoning_parser='gemma4', max_model_len=32768, dtype='bfloat16',
                     gpu_memory_utilization=0.90, enable_auto_tool_choice=True,
                     enable_lora=False, scheduler_reserve_full_isl=False,
                     tensor_parallel_size=tp, startup_timeout=60 * 20, extra_args=tuple(extra))
    t0 = time.time()
    srv = VllmServer(cfg)
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


@phase('8_isolation')
def isolation(code):
    """Unprivileged agent and evaluator uids; controller dirs 0700 (docs/decisions.md D3)."""
    out = {}
    for u in [f'tgagent{i}' for i in range(8)] + ['tgeval']:
        out[f'useradd_{u}'] = sh(f'id {u} || useradd -M -s /bin/bash {u}; id {u}')
    # experiment code and kernel source readable by root only; the running script is already
    # in memory, so its source file is removed when possible
    out['src_before'] = sh('ls -la /kaggle/src 2>&1 | head -5')
    out['src_remove'] = sh('chmod -R go-rwx /kaggle/src 2>&1; rm -f /kaggle/src/*.py 2>&1; ls -la /kaggle/src 2>&1 | head -5')
    sh(f'chmod -R go-rwx {code}; chmod 711 /kaggle/working')
    bank = code / 'bank'
    # the evaluator uid needs the oracles; give it the bank but keep everything else root-only
    sh(f'chown -R tgeval:tgeval {bank} && chmod -R go-rwx {bank} && chmod 711 {code}')
    for d in ('/kaggle/working/results', '/kaggle/working/code'):
        sh(f'mkdir -p {d}')
    sh('chmod 700 /kaggle/working/results')
    work = Path('/tmp/wk'); work.mkdir(exist_ok=True); work.chmod(0o711)
    sp = 'setpriv --reuid=tgagent0 --regid=tgagent0 --clear-groups --no-new-privs --'
    oracle = next((code / 'bank' / 'templates').glob('*/oracle/oracle.py'))
    out['agent_reads_oracle'] = sh(f'{sp} cat {oracle} >/dev/null 2>&1; echo rc=$?')
    out['agent_lists_results'] = sh(f'{sp} ls /kaggle/working/results >/dev/null 2>&1; echo rc=$?')
    out['agent_lists_bank'] = sh(f'{sp} ls {bank} >/dev/null 2>&1; echo rc=$?')
    out['agent_reads_harness'] = sh(f'{sp} cat {code}/harness/loop.py >/dev/null 2>&1; echo rc=$?')
    out['agent_reads_kernel_src'] = sh(f'{sp} ls /kaggle/src >/dev/null 2>&1; echo rc=$?')
    out['iptables'] = sh('for u in tgagent0 tgagent1 tgagent2 tgagent3 tgagent4 tgagent5 tgagent6 tgagent7 tgeval; do iptables -A OUTPUT -o lo -p tcp --dport 8000 -m owner --uid-owner $u -j REJECT; done 2>&1; echo rc=$?')
    out['eval_reaches_vllm_port'] = sh("setpriv --reuid=tgeval --regid=tgeval --clear-groups --no-new-privs -- python3 -c \"import socket;s=socket.socket();s.settimeout(2);print(s.connect_ex(('127.0.0.1',8000)))\" 2>&1")
    out['agent_reaches_vllm_port'] = sh(f"{sp} python3 -c \"import socket;s=socket.socket();s.settimeout(2);print(s.connect_ex(('127.0.0.1',8000)))\" 2>&1")
    ISO.update(out)
    return out


def run_runner(code, port, mode):
    import shlex
    env_id = ('kaggle-L4x4|' + sh("nvidia-smi --query-gpu=name --format=csv,noheader | sort | uniq -c | tr -s ' '")
              + '|img:37c64f7d|vllm0.19.1|tp4|model:52f3f65-overlay')
    out_dir = Path('/kaggle/working/results') / mode
    if mode == 'runner_smoke':
        spec = Path('/tmp/fixture_spec.csv')
        fb = Path('/tmp/fixture_bank'); fb.mkdir(exist_ok=True)
        dst = fb / 'FIXTURE.m1_toy'
        if not dst.exists():
            shutil.copytree(code / 'tests' / 'fixtures' / 'tpl_m1', dst)
            m = json.loads((dst / 'template.json').read_text())
            m['issue_paraphrases'] = [m['problem_statement']] * 4
            (dst / 'template.json').write_text(json.dumps(m))
            sh(f'chown -R tgeval:tgeval {fb} && chmod -R go-rwx {fb}')
        spec.write_text('template_id,split,family,mechanism\nFIXTURE.m1_toy,pilot,logistics,M1\n')
        extra = ['--bank', str(fb), '--spec', str(spec), '--limit', '6', '--concurrency', '3']
    else:
        extra = ['--concurrency', '8']
    cmd = [sys.executable, str(code / 'runner' / 'runner.py'), '--split', 'pilot',
           '--replicates', '1', '--out', str(out_dir), '--work', '/tmp/wk',
           '--base-url', f'http://127.0.0.1:{port}/v1', '--model', SERVED[port],
           '--model-revision', R['verified_revision'],
           '--run-as', ','.join(f'tgagent{i}' for i in range(8)), '--eval-user', 'tgeval', '--environment-id', env_id,
           '--code-commit', CODE_COMMIT, *extra]
    t0 = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(code))
    res = {'cmd': ' '.join(shlex.quote(c) for c in cmd), 'rc': r.returncode,
           'wall_seconds': round(time.time() - t0, 1), 'stdout_tail': r.stdout[-2000:],
           'stderr_tail': r.stderr[-3000:]}
    csvp = out_dir / 'runs.csv'
    if csvp.exists():
        import csv as _csv
        rows = list(_csv.DictReader(open(csvp)))
        res['n_rows'] = len(rows)
        res['status_counts'] = {s: sum(1 for x in rows if x['status'] == s)
                                for s in {x['status'] for x in rows}}
        res['mean_elapsed_s'] = round(sum(float(x['elapsed_seconds'] or 0) for x in rows) / max(1, len(rows)), 1)
        res['mean_turns'] = round(sum(float(x['turns'] or 0) for x in rows) / max(1, len(rows)), 1)
        # BLIND: no W/F by framing is printed here (protocol 9.2); pooled rates only via --pilot.
    shutil.copytree(out_dir, f'/kaggle/working/out_{mode}', dirs_exist_ok=True)
    return res


if __name__ == '__main__':
    gpu_guard()
    install_wheels()
    procs = []
    try:
        code = code_dir()
        isolation(code)
        MODEL = model_path()
        R['model_path'] = str(MODEL)

        @phase('2_server_tp4')
        def up():
            p, secs, ex = start_server(4, '0,1,2,3', 8000, 'tp4_8000')
            procs.append(p)
            return {'load_seconds': secs, 'served': SERVED, 'extra_args': ex}
        h = model_hashes()
        if h['ok'] and h.get('all_match'):
            R['verified_revision'] = '52f3f65bc7a02d555763bc923bd1d9094898219d'
        else:
            raise SystemExit('served model files do not match HF 52f3f65: refusing to run')
        if up()['ok']:
            phase(f'9_runner_{MODE}')(lambda: run_runner(code, 8000, MODE))()
    finally:
        stop(procs)
        R['finished'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        save()
        print('DONE', flush=True)
