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
import shlex
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
MODE = 'runner_smoke'   # 'runner_smoke' (toy fixture, 6 runs), 'pilot' (72 + 9) or 'confirmatory'; build --define
# confirmatory only (build --define; fail closed when missing or inconsistent):
S_REPLICATES = ''        # seeds per paraphrase S from the 9.3 rule ('2', '3' or '4'), = freeze
FROZEN_COMMIT = ''       # commit holding freeze/manifest.json: the bundle must be built from it
FREEZE_SHA256 = ''       # SHA-256 of freeze/manifest.json (the stamped hash)
SHARD = ''               # 'i/N': parallel kernels, each runs every N-th sector block
SESSION = ''             # 1, 2, ... within a shard; session k > 1 resumes session k - 1
SCRIPT_SHA256 = ''       # set by build_kernel: SHA-256 of this script at the commit, pre-define
# D13 (x2) runs on Google Colab with one A100; the Kaggle modes never change (build --define):
PLATFORM = 'kaggle'      # 'kaggle' (L4x4, TP=4, offline) or 'colab' (1x A100, TP=1, see colab_*)
COLAB_GPU_MEM = '0.90'   # colab: vLLM gpu_memory_utilization of the budget card (Kaggle keeps 0.90)
# Colab hands out 40 or 80 GB A100s. x3 runs on the 80 GB card only, at 0.90 (smoke 4: the 40 GB
# budget leaves a 15k-token KV cache, 2.9 requests of 32k; Kaggle's L4x4 at 0.90 is comparable to
# the 80 GB card), so every chained session has the same card and budget (Astra/Sol, D15).
# Smokes keep the 40 GB budget on either card.
COLAB_BUDGET_MIB = 40960
COLAB_X3_MIB = 81920
COLAB_MODES = ('runner_smoke', 'x3', 'ladder')  # the only modes allowed on Colab (D15, D17)
COLAB_80GB_MODES = ('x3', 'ladder')   # x3's card and budget (D17 runs on x3's host)
KERNEL_T0 = time.time()
SESSION_LIMIT_S = 12 * 3600      # Kaggle GPU session limit
STOP_MARGIN_S = 90 * 60          # no run starts later than this before the limit (60 min budget + eval)
AGENTS = [f'tgagent{i}' for i in range(8)]
EVALS = [f'tgeval{i}' for i in range(8)]
UDS_DIR = Path('/root/tgv')      # vLLM listens ONLY on a root-only Unix socket
UDS = UDS_DIR / 'vllm.sock'
DIVERSITY_REPLICATES = 3         # 9.1 seed diversity: r2..r4 on one pilot template, paraphrase 1
RESUME_SHA256 = ''               # build --define: expected hash of a previous results_sealed.tar.gz
# D12 exploratory modes 'x1_calibration' and 'x1_transfer' (added after the freeze; build --define):
X1_MANIFEST_SHA256 = ''          # SHA-256 of explore/x1_manifest.json (OTS-stamped with D12)
X1_RUNG = ''                     # x1_transfer: the rung chosen by the sealed selector
X1_SELECTION_SHA256 = ''         # x1_transfer: hash of the calibration kernel's x1_selection.json
X1_STOP_AT_EPOCH = ''            # x1_transfer: no run starts after it (D12: Wed 11 02:00 Chile)
X1_CUTOFF_S = ''                 # x1 modes: no run starts later than this after kernel start (6 h cap)
X1_HARD_S = ''                   # x1 modes: the runner is stopped at this time after kernel start;
                                 # unfinished runs are closed out (infra_failed), like a time cut
X1_SESSION_S = ''                # x1 modes: absolute end of the whole session (= hard + overhead);
                                 # a watchdog ends the process there (the last sealed checkpoint stays)
# D15 explicit-request follow-up 'x3' (Colab only; build --define): sessions chain like the
# confirmatory (SESSION k resumes k-1 with RESUME_SHA256); no run starts after the sealed stop
# time; unfinished runs are closed out only once it has passed
X3_MANIFEST_SHA256 = ''          # SHA-256 of the mode's sealed manifest (x3: D15, e4b: D16)
# D16 'e4b': the same sealed follow-up machinery (blocks, chained sessions, stop time, hang watch)
# on Kaggle L4x4 with Gemma 4 E4B (same QAT w4a16 family) instead of the 31B; never pooled
# D17 'ladder': the same machinery on Colab (x3's A100 80 GB) with three models in sealed blocks,
# one server at a time (26B-A4B, E2B, E4B from their pinned HF revisions; no overlay)
FOLLOWUP_MODES = ('x3', 'e4b', 'ladder')
FOLLOWUP_MANIFEST = {'x3': 'followup/x3_manifest.json', 'e4b': 'followup/e4b_manifest.json',
                     'ladder': 'followup/ladder_manifest.json'}
R = {'started': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'phases': {}}
HF_EXPECTED = {  # google/gemma-4-31B-it-qat-w4a16-ct @ 52f3f65bc7a02d555763bc923bd1d9094898219d
    'model.safetensors': ('sha256', '1b9b1d622a93f02c0d33f98e502f233b5d707443af6ddc464ed0bf5498506c20'),
    'tokenizer.json': ('sha256', 'cc8d3a0ce36466ccc1278bf987df5f71db1719b9ca6b4118264f45cb627bfe0f'),
    'config.json': ('git', 'e8beda78f4e93f78a5d9d8f2b78cd9bc272d35e5'),
    'chat_template.jinja': ('git', '4741bf6e4132ba23a5537f9d6e74e9a6d613d7cd'),
    'generation_config.json': ('git', 'f6bc6f4146a610a3881015c90d36a78beb1333bb'),
    'tokenizer_config.json': ('git', 'b22e2c5c05597a7e8c0cb1cebdb7d45570772005'),
}
HF_EXPECTED_E4B = {  # google/gemma-4-E4B-it-qat-w4a16-ct @ 6cd26aaa2357fb2bad8c51699a7558a4d1a965bb
    'model.safetensors': ('sha256', '19d89d2a4b3e401a3eae75ec08ab112810421a036c91d8c8226b686be7fe0c5d'),
    'tokenizer.json': ('sha256', 'cc8d3a0ce36466ccc1278bf987df5f71db1719b9ca6b4118264f45cb627bfe0f'),
    'config.json': ('git', 'cc8c5ca64e33c073a961fc35777c38badb2efd52'),
    'chat_template.jinja': ('git', 'fbe3b59b625cd1b8850ea592d4203df6ec04684b'),
    'generation_config.json': ('git', 'f6bc6f4146a610a3881015c90d36a78beb1333bb'),
    'tokenizer_config.json': ('git', 'b22e2c5c05597a7e8c0cb1cebdb7d45570772005'),
}
HF_EXPECTED_26B = {  # google/gemma-4-26B-A4B-it @ 4d7ae4984b7db7de8f8457170b3f1a419ee76d52 (bf16; no
    # QAT w4a16 release exists for it; the 12B QAT uses Gemma4Unified, not in vLLM 0.19.1: D17)
    'model-00001-of-00002.safetensors': ('sha256', '1127684971bbca40465435a5cad69d67ad603bf5e61c6dfd5561fae4a3bcfdb3'),
    'model-00002-of-00002.safetensors': ('sha256', 'aab47033e1e8a492ef8e581efae1cf36478d0433567e7729b3c1728bc8970db7'),
    'model.safetensors.index.json': ('git', '889ab10e12aca96c43c9804a041fb1780de1e5ca'),
    'tokenizer.json': ('sha256', 'cc8d3a0ce36466ccc1278bf987df5f71db1719b9ca6b4118264f45cb627bfe0f'),
    'config.json': ('git', 'f42adcca257bb0865c506947671e7d0af52ac9c4'),
    'chat_template.jinja': ('git', '4741bf6e4132ba23a5537f9d6e74e9a6d613d7cd'),
    'generation_config.json': ('git', 'e605bb4523b1462ea9d9a3810b9e3ecf7ab7b1f6'),
    'tokenizer_config.json': ('git', '6068e357379d36f823c377e30efb101fa2c67fe4'),
}
HF_EXPECTED_E2B = {  # google/gemma-4-E2B-it-qat-w4a16-ct @ 971342c08f607aa7779983f6b5289778b5d271a7
    'model.safetensors': ('sha256', '93177bfc1b53823f2e01c7cebc3b94f65d189e373a647d086112f614ba448ab9'),
    'tokenizer.json': ('sha256', 'cc8d3a0ce36466ccc1278bf987df5f71db1719b9ca6b4118264f45cb627bfe0f'),
    'config.json': ('git', 'c7120a8f546e2f99342716f13fd97e57f9abbad4'),
    'chat_template.jinja': ('git', 'fbe3b59b625cd1b8850ea592d4203df6ec04684b'),
    'generation_config.json': ('git', 'f6bc6f4146a610a3881015c90d36a78beb1333bb'),
    'tokenizer_config.json': ('git', 'b22e2c5c05597a7e8c0cb1cebdb7d45570772005'),
}
MODEL_SPECS = {
    '31b': {'kaggle': 'gemma-4-31b-it-qat-w4a16-ct/2', 'dest': '/kaggle/working/model_52f3f65',
            'overlay': 'notebooks/model_overlay', 'hf': HF_EXPECTED,
            'revision': '52f3f65bc7a02d555763bc923bd1d9094898219d', 'tag': 'model:52f3f65-overlay'},
    'e4b': {'kaggle': 'gemma-4-e4b-it-qat-w4a16-ct/2', 'dest': '/kaggle/working/model_e4b_6cd26aa',
            'overlay': 'notebooks/e4b_overlay', 'hf': HF_EXPECTED_E4B,
            'revision': '6cd26aaa2357fb2bad8c51699a7558a4d1a965bb', 'tag': 'model:e4b-6cd26aa-overlay'},
    # D17 ladder: downloaded by the Colab bootstrap from HF at the pinned revision into
    # /kaggle/input/hf/<hf_dir>; served as is (every file hash-checked, no overlay)
    '26b_a4b': {'hf_repo': 'google/gemma-4-26B-A4B-it', 'hf_dir': 'gemma-4-26b-a4b@4d7ae49',
                'dest': '/kaggle/working/model_26b_a4b_4d7ae49', 'hf': HF_EXPECTED_26B,
                'revision': '4d7ae4984b7db7de8f8457170b3f1a419ee76d52', 'tag': 'model:26b-a4b-4d7ae49'},
    'e2b': {'hf_repo': 'google/gemma-4-E2B-it-qat-w4a16-ct', 'hf_dir': 'gemma-4-e2b@971342c',
            'dest': '/kaggle/working/model_e2b_971342c', 'hf': HF_EXPECTED_E2B,
            'revision': '971342c08f607aa7779983f6b5289778b5d271a7', 'tag': 'model:e2b-971342c'},
    'e4b_hf': {'hf_repo': 'google/gemma-4-E4B-it-qat-w4a16-ct', 'hf_dir': 'gemma-4-e4b@6cd26aa',
               'dest': '/kaggle/working/model_e4b_6cd26aa_hf', 'hf': HF_EXPECTED_E4B,
               'revision': '6cd26aaa2357fb2bad8c51699a7558a4d1a965bb', 'tag': 'model:e4b-6cd26aa'},
}
LADDER_KINDS = ('e4b_hf', 'e2b', '26b_a4b')
LADDER_KIND = ''         # D17: the model of the ladder block being served (set by ladder_switch)


MODEL_KIND = ''          # build --define MODEL_KIND=e4b: a runner_smoke on Kaggle with E4B (D16
                         # start-up check: load, generation, tool calls on the toy fixture only)


def model_spec():
    if MODE == 'ladder':
        if LADDER_KIND not in LADDER_KINDS:
            raise RuntimeError(f'ladder: no model selected ({LADDER_KIND!r})')
        return MODEL_SPECS[LADDER_KIND]
    return MODEL_SPECS['e4b' if MODE == 'e4b' or MODEL_KIND == 'e4b' else '31b']


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
                                     'error': redact(f'{type(exc).__name__}: {exc}'),
                                     'trace': redact(traceback.format_exc()[-3000:])}
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
    if PLATFORM != 'colab' and MODE in ('x3', 'ladder'):
        raise SystemExit(f'{MODE} runs on Colab only (its sealed environment)')
    if PLATFORM == 'colab':
        if MODE not in COLAB_MODES:
            raise SystemExit(f'mode {MODE!r} never runs on Colab')
        if len(gpus) != 1 or 'A100' not in gpus[0]:
            info['abort'] = True
            R['phases']['0_gpu_guard'] = {'ok': False, **info}
            save()
            raise SystemExit(f'GPU mismatch (Colab needs one A100), aborting: {gpus}')
        R['colab_gpu'] = gpus[0]          # 40 or 80 GB: recorded, one environment id for both
        if MODE in COLAB_80GB_MODES and f', {COLAB_X3_MIB} MiB' not in gpus[0]:
            info['abort'] = True
            R['phases']['0_gpu_guard'] = {'ok': False, **info}
            save()
            raise SystemExit(f'{MODE} needs the 80 GB A100 (reconnect for another card): {gpus}')
        return info
    if len(gpus) != 4 or not all('L4' in g for g in gpus):
        info['abort'] = True
        R['phases']['0_gpu_guard'] = {'ok': False, **info}
        save()
        raise SystemExit(f'GPU mismatch, aborting: {gpus}')
    return info


# ------------------------------------------------------------------ 1 wheels
@phase('1_wheels')
def install_wheels():
    if PLATFORM == 'colab':
        return colab_install()
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
    spec = model_spec()
    if 'hf_dir' in spec:                      # D17: HF files at the pinned revision, no overlay
        src = Path('/kaggle/input/hf') / spec['hf_dir']
        if not src.is_dir():
            raise FileNotFoundError(f"model input hf/{spec['hf_dir']} not downloaded")
        KAGGLE_MODEL = src
        dest = Path(spec['dest'])
        dest.mkdir(parents=True, exist_ok=True)
        for f in src.iterdir():
            if f.is_file() and not (dest / f.name).exists():
                os.symlink(f, dest / f.name)
        return dest
    c = glob.glob(f"/kaggle/input/**/{spec['kaggle']}", recursive=True)
    if not c:
        raise FileNotFoundError(f"model input {spec['kaggle']} not attached")
    KAGGLE_MODEL = Path(c[0])
    dest = Path(spec['dest'])
    dest.mkdir(parents=True, exist_ok=True)
    overlay = code_dir() / spec['overlay']
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


def colab_gpu_util():
    """Smokes: COLAB_GPU_MEM of a 40 GB card as a fraction of this one (0.90 on 40 GB, 0.45 on
    80 GB). x3: 0.90 of the 80 GB card, the only card it runs on."""
    total = int(sh('nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits').split()[0])
    if MODE in COLAB_80GB_MODES and total != COLAB_X3_MIB:
        raise RuntimeError(f'{MODE} needs the 80 GB A100, got {total} MiB')
    util = round(float(COLAB_GPU_MEM) * (COLAB_X3_MIB if MODE in COLAB_80GB_MODES else COLAB_BUDGET_MIB)
                 / total, 4)
    if not 0.3 <= util <= float(COLAB_GPU_MEM):
        raise RuntimeError(f'unexpected A100 memory {total} MiB')
    R['colab_vllm_budget'] = {'total_mib': total, 'gpu_memory_utilization': util,
                              'budget_mib': round(util * total)}
    return util


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
                     gpu_memory_utilization=colab_gpu_util() if PLATFORM == 'colab' else 0.90,
                     enable_auto_tool_choice=True,
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


def model_hash_check():
    out = {'files': sorted(p.name for p in MODEL.iterdir()), 'served_dir': str(MODEL),
           'kaggle_dir': str(KAGGLE_MODEL)}
    expected_files = model_spec()['hf']
    for name, (kind, expected) in expected_files.items():
        p = MODEL / name
        if not p.exists():
            out[name] = 'missing'
            continue
        got = sha256(p) if kind == 'sha256' else git_blob_sha1(p)
        out[name] = {'match': got == expected, 'got': got}
    out['all_match'] = all(isinstance(v, dict) and v['match'] for k, v in out.items()
                           if k in expected_files)
    return out


model_hashes = phase('7_model_hashes')(model_hash_check)


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
    """Run cmd as uid u; on Colab inside a fresh, empty network namespace, exactly the
    context agents and evaluators run in (the runner itself starts in one, see runner_cmd)."""
    netns = ' '.join(COLAB_NETNS) + ' ' if PLATFORM == 'colab' else ''
    return sh(f'{netns}setpriv --reuid={u} --regid={u} --clear-groups --no-new-privs -- '
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
    if PLATFORM == 'colab':
        out['net_lock'] = colab_netns_check()
        out['hide'] = colab_hide()
    work = Path('/tmp/wk'); work.mkdir(exist_ok=True); work.chmod(0o711)
    oracle = next((code / 'bank' / 'templates').glob('*/oracle/oracle.py'))
    probes = {'kernel_src_ls': 'ls /kaggle/src', 'kernel_src_cat': 'cat /kaggle/src/script.py',
              'inputs_ls': 'ls /kaggle/input', 'working_ls': 'ls /kaggle/working',
              'oracle_cat': f'cat {oracle}', 'bank_ls': f'ls {code}/bank/templates',
              'harness_cat': f'cat {code}/harness/loop.py', 'root_ls': 'ls /root',
              'uds_dir_ls': f'ls {UDS_DIR}', 'tmp_ls': 'ls /tmp', 'wk_ls': 'ls /tmp/wk',
              'var_tmp_ls': 'ls /var/tmp', 'shm_ls': 'ls /dev/shm'}
    if PLATFORM == 'colab':
        probes.update(COLAB_DENIED)
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
    if PLATFORM == 'colab' and reach:                # Colab: all egress of the uid is rejected
        failures.append(f'tcp reachable on colab: {reach}')
    # Unix sockets with a path (vLLM engine ZMQ ipc carries serialized objects): an agent
    # that could connect would reach root code paths -> abort. Abstract ones are recorded.
    paths, abstract = set(), 0
    typed = set()                                    # (path or @abstract, socket type) for Colab
    for line in Path('/proc/net/unix').read_text().splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 8:
            typed.add((parts[7], int(parts[4], 16)))
            if parts[7].startswith('@'):
                abstract += 1
            else:
                paths.add(parts[7])
    connectable = []
    if PLATFORM == 'colab':
        connectable = colab_unix_reach(typed)
    for path in sorted(paths) if PLATFORM != 'colab' else ():
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


def served_model():
    """Served model id; after stop() (close-out, CPU only) the id recorded at start-up or
    the one in the resumed manifest."""
    if 8000 in SERVED:
        return SERVED[8000]
    if R.get('served_model'):
        return R['served_model']
    man = RESULTS_DIR / 'confirmatory' / 'manifest.json'
    if man.exists():
        return json.loads(man.read_text())['model']
    if R.get('model_path'):
        # the server never started in any session: vLLM serves the model under its path
        return R['model_path']
    raise RuntimeError('no served model id known')


def environment_id(kind=None):
    if PLATFORM == 'colab' and MODE == 'ladder':
        return 'colab-A100|py3.12|vllm0.19.1|tp1|' + MODEL_SPECS[kind or LADDER_KIND]['tag']
    if PLATFORM == 'colab':
        # one id for the 40 and the 80 GB A100 (both GA100, sm_80); the card is in R['colab_gpu']
        return 'colab-A100|py3.12|vllm0.19.1|tp1|model:52f3f65-overlay'
    return ('kaggle-L4x4|' + sh("nvidia-smi --query-gpu=name --format=csv,noheader | sort | uniq -c | tr -s ' '")
            + '|img:37c64f7d|vllm0.19.1|tp4|' + model_spec()['tag'])


def runner_cmd(code, mode, out_dir, extra):
    blk = next((b for b in x3_blocks() if b['name'] == out_dir.name), None) if MODE == 'ladder' else None
    kind = (blk['model'] if blk else LADDER_KIND) if MODE == 'ladder' else None
    env_id = environment_id(kind) if MODE == 'ladder' else environment_id()
    if blk is not None and env_id != blk['environment_id']:
        raise RuntimeError(f'environment {env_id!r} differs from the D17 block {out_dir.name}')
    if mode == 'confirmatory' and env_id != FREEZE['environment_id']:
        raise RuntimeError(f'environment {env_id!r} differs from the frozen {FREEZE["environment_id"]!r}')
    if mode.startswith('x1_') and env_id != X1['environment_id']:
        raise RuntimeError(f'environment {env_id!r} differs from the D12 {X1["environment_id"]!r}')
    if mode == 'x3' and MODE != 'ladder' and env_id != X3['environment_id']:
        raise RuntimeError(f'environment {env_id!r} differs from the D15 {X3["environment_id"]!r}')
    split = 'confirmatory' if mode in ('confirmatory', 'x1_transfer', 'x3') else 'pilot'
    args = ['--split', split, '--out', str(out_dir), '--work', '/tmp/wk',
            '--base-url', f'unix:{UDS}',
            # D17: each block's model and revision from the sealed manifest (also in a close-out)
            '--model', MODEL_SPECS[kind]['dest'] if kind else served_model(),
            '--model-revision', MODEL_SPECS[kind]['revision'] if kind else R['verified_revision'],
            '--run-as', ','.join(AGENTS), '--eval-user', ','.join(EVALS),
            '--concurrency', str(len(AGENTS)), '--environment-id', env_id,
            '--code-commit', CODE_COMMIT,
            '--stop-at', str(stop_at()), *extra]
    if mode in ('confirmatory', 'x1_transfer'):
        args += ['--shard', SHARD]
    # arguments go through a root-only file: the process list is visible to every uid
    argf = UDS_DIR / f'args_{out_dir.name}'
    argf.write_text('\n'.join(args) + '\n')
    cmd = [sys.executable, str(code / 'runner' / 'runner.py'), f'@{argf}']
    # Colab: the runner (root) and every agent/evaluator it starts live in a fresh network
    # namespace with no interface but a down loopback: no internet, no host services, no
    # abstract sockets of the host; the model is reached through the Unix socket's path
    return (COLAB_NETNS + cmd) if PLATFORM == 'colab' else cmd


RUN_ID_RE = re.compile(r'(pilot|confirmatory|runner_smoke):[\w.]+:[NPA]:p\d+:r\d+'
                       r'|(pilot|confirmatory|runner_smoke)__[\w.]+__[NPA]__p\d+__r\d+')


def redact(text):
    """Open outputs never carry run ids (they contain the framing)."""
    return RUN_ID_RE.sub('<run>', text or '')


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
# raw results (framings, logs): exported with the session for the frozen modes; for the x1
# modes they live in a root-only directory OUTSIDE /kaggle/working, so a watchdog exit can
# never leave them in the output (only the sealed archive and blind summaries are exported)
RESULTS_DIR = Path('/root/tgv/results') if MODE.startswith(('x1_', 'x3', 'e4b', 'ladder')) else Path('/kaggle/working/results')
SEAL_LOCK = threading.Lock()     # one snapshot/seal at a time (periodic and final)
TMP_LOCK = threading.Lock()      # short lock: creating, replacing or sweeping a .sealed_*.tmp
CLOSING = threading.Event()      # x1 watchdog: no new temporary archive after this is set
OPEN_TMPS = set()                # temporary archives being written in /kaggle/working


def snapshot_and_seal(kind='periodic'):
    """Consistent snapshot, then an atomic durable replace of the sealed archive (the previous
    archive stays valid until the new one is complete).
    Consistency: every event in attempts.jsonl refers to files written BEFORE the event, so
    each block's attempts.jsonl is copied FIRST and its other files afterwards: every logged
    event finds its files in the snapshot (later extra files are harmless checkpoints)."""
    with SEAL_LOCK:
        return _snapshot_and_seal(kind)


def _snapshot_and_seal(kind):
    import tarfile, tempfile
    res_dir = RESULTS_DIR
    with TMP_LOCK:
        if CLOSING.is_set():
            raise RuntimeError('session closing: no new snapshot')
        fd, tmp_name = tempfile.mkstemp(prefix='.sealed_', suffix='.tmp', dir='/kaggle/working')
        OPEN_TMPS.add(tmp_name)
    tmp = Path(tmp_name)
    stage = Path(tempfile.mkdtemp(prefix='snap_', dir='/root/tgv'))
    try:
        for top in sorted(f for f in res_dir.iterdir() if f.is_file() and not f.name.endswith('.tmp')):
            shutil.copy2(top, stage / top.name)    # x3_sessions.jsonl (Astra/Sol: the resume chain)
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
        # periodic snapshots may miss events after them; a resume records which kind it used
        (stage / 'seal.json').write_text(json.dumps({'kind': kind, 'utc': time.time()}))
        with os.fdopen(fd, 'wb') as raw:
            fd = None
            with tarfile.open(fileobj=raw, mode='w:gz') as t:
                t.add(stage, arcname='results')
            raw.flush()
            os.fsync(raw.fileno())
        with TMP_LOCK:
            if CLOSING.is_set():
                raise RuntimeError('session closing: archive not published')
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
        with TMP_LOCK:
            tmp.unlink(missing_ok=True)      # no-op after a successful replace
            OPEN_TMPS.discard(tmp_name)
        shutil.rmtree(stage, ignore_errors=True)


def checkpoint():
    R['last_checkpoint'] = {'utc': time.strftime('%H:%M:%S', time.gmtime()),
                            'sha256': snapshot_and_seal()}
    save()


# vLLM 0.19.1's gemma4 tool parser can loop forever on some array arguments (Kaggle forum,
# reported with E4B) and freeze the whole server. The sealed harness waits up to the episode's
# remaining budget for each call and then records budget_exhausted, so a hung server would turn
# every later run of the session into a budget row. In the hang-watched modes the kernel probes
# /health; after HANG_FAILS consecutive failures the runner and every agent/evaluator process are
# killed (no final row for the runs in flight: their started try stays counted, as for any crashed
# session) and the session ends sealed, to be resumed by the next one.
HANG_WATCH_MODES = ('x3',)   # D17 blocks run through run_block(..., 'x3', ...): watched too
HANG_PROBE_S = 60
HANG_PROBE_TIMEOUT_S = 30
HANG_FAILS = 5


def server_healthy():
    try:
        return uds_request('GET', '/health', timeout=HANG_PROBE_TIMEOUT_S)[0] == 200
    except Exception:
        return False


def kill_runner(proc):
    try:
        os.killpg(proc.pid, 9)
    except (ProcessLookupError, PermissionError):
        pass
    for u in AGENTS + EVALS:
        sh(f'pkill -9 -u {u}')


def hang_watch(proc, done):
    state = {'fired_utc': None, 'first_failure_utc': None, 'failures': 0, 'probes': 0}

    def run():
        while not done.wait(HANG_PROBE_S):
            if proc.poll() is not None:
                return
            state['probes'] += 1
            healthy = server_healthy()
            if done.is_set() or proc.poll() is not None:
                return                # the runner ended while the probe waited (Astra)
            if healthy:
                state['failures'], state['first_failure_utc'] = 0, None
                continue
            state['failures'] += 1
            state['first_failure_utc'] = state['first_failure_utc'] or time.time()
            if state['failures'] >= HANG_FAILS:
                state['fired_utc'] = time.time()
                kill_runner(proc)
                return
    state['thread'] = threading.Thread(target=run, daemon=True)
    state['thread'].start()
    return state


def run_block(code, mode, name, extra, hard_at=None, out_root=None):
    out_dir = (out_root or RESULTS_DIR) / name
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
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            cwd=str(code), start_new_session=True)
    # never during a close-out: it runs on the CPU after the server is stopped (Astra/Sol/Argon)
    hang = hang_watch(proc, done) if mode in HANG_WATCH_MODES and '--close-out' not in extra \
        else None
    try:
        try:
            out, err = proc.communicate(
                timeout=None if hard_at is None else max(1.0, hard_at - time.time()))
            r = subprocess.CompletedProcess(cmd, proc.returncode, out, err)
        except subprocess.TimeoutExpired:
            # x1 hard limit: the runner is killed, then every agent/evaluator process
            kill_runner(proc)
            out, err = proc.communicate()
            r = subprocess.CompletedProcess(cmd, 'hard_limit', out, err)
    finally:
        done.set()
        th.join()        # a checkpoint in progress always finishes before anything else
        if hang is not None:
            hang['thread'].join()
    if hang is not None and hang['fired_utc']:
        r = subprocess.CompletedProcess(cmd, 'server_hang', r.stdout, r.stderr)
    # full output sealed with the results; only redacted tails stay in the open
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f'runner_output_{int(t0)}.txt').write_text(r.stdout + '\n--- stderr ---\n' + r.stderr)
    res = {'rc': r.returncode, 'wall_seconds': round(time.time() - t0, 1),
           'stdout_tail': redact(r.stdout[-1500:]), 'stderr_tail': redact(r.stderr[-3000:])}
    R.setdefault('blocks', {})[name] = res
    if r.returncode == 'hard_limit':
        res['hard_limit_hit'] = True
        return res
    if r.returncode == 'server_hang':
        res['server_hang'] = {k: v for k, v in hang.items() if k != 'thread'}
        raise RuntimeError(f'model server stopped answering /health during {name}: runner '
                           f'stopped, session ends sealed (resume in the next session)')
    if r.returncode != 0:
        raise RuntimeError(f'runner block {name} failed rc={r.returncode}: {redact(r.stderr[-1500:])}')
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
    logs = RESULTS_DIR / name / 'logs'
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
    res_dir = RESULTS_DIR
    # confirmatory: no blind CSV at all (with the public order and a time cut, the status of
    # template/paraphrase/replicate rows can reveal framings); it stays sealed until decoding
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
    digest = snapshot_and_seal('final')   # nothing is writing any more: final and complete
    shutil.rmtree(res_dir)
    return {'sealed': str(SEALED), 'sha256': digest, 'bytes': SEALED.stat().st_size}


def restore_previous():
    """Resume: a previous version's sealed results attached as a kernel source."""
    prev = glob.glob('/kaggle/input/**/results_sealed.tar.gz', recursive=True)
    if MODE == 'x1_transfer':
        # the attached input is the calibration kernel (its selection); never a resume
        if RESUME_SHA256:
            raise RuntimeError('x1_transfer never resumes')
        return {'resumed_from': None, 'attached_not_restored': [sha256(x) for x in prev]}
    if not RESUME_SHA256:
        if prev:
            raise RuntimeError(f'sealed results attached but no RESUME_SHA256 defined: {prev}')
        return {'resumed_from': None}
    match = [x for x in prev if sha256(x) == RESUME_SHA256]
    if len(match) != 1:
        raise RuntimeError(f'expected exactly one sealed archive with sha256 {RESUME_SHA256}: {prev}')
    import tarfile
    with tarfile.open(match[0]) as t:
        t.extractall(RESULTS_DIR.parent)          # the archive holds results/
    seal = RESULTS_DIR / 'seal.json'
    kind = json.loads(seal.read_text()) if seal.exists() else {'kind': 'unknown'}
    seal.unlink(missing_ok=True)
    return {'resumed_from': match[0], 'sha256': RESUME_SHA256, 'parent_seal': kind}


def session_chain(restored):
    """Confirmatory sessions form one chain per shard: session 1 starts empty; session k
    resumes exactly session k-1 of the same shard and freeze. Appends this session's entry
    (with the parent's seal kind: a periodic snapshot may have lost later events, which
    were then re-run; declared, never hidden)."""
    out = RESULTS_DIR / 'confirmatory'
    log = out / 'sessions.jsonl'
    k = int(SESSION)
    if k == 1:
        if out.exists():
            raise RuntimeError('session 1 must start without confirmatory results')
        prev = None
    else:
        if not log.exists():
            raise RuntimeError('resumed archive has no confirmatory session log')
        if not (out / 'manifest.json').exists() and (
                (out / 'attempts.jsonl').exists() or (out / 'episodes').exists()):
            raise RuntimeError('resumed archive has run records without the runner manifest')
        # no manifest and no records: the previous session(s) never reached the runner (e.g.
        # the server failed to start); an empty, resumable session, declared in the chain
        prev = json.loads(log.read_text().strip().splitlines()[-1])
        if (prev['session'], prev['shard'], prev['freeze_sha256']) != (k - 1, SHARD, FREEZE_SHA256):
            raise RuntimeError(f'resume chain broken: previous entry {prev}, this session {k} {SHARD}')
    out.mkdir(parents=True, exist_ok=True)
    entry = {'session': k, 'shard': SHARD, 'freeze_sha256': FREEZE_SHA256,
             'code_commit': CODE_COMMIT, 'parent_sha256': RESUME_SHA256 or None,
             'parent_seal': restored.get('parent_seal'),
             'parent_reached_runner': (out / 'manifest.json').exists() if k > 1 else None,
             'started_utc': KERNEL_T0,
             'stop_at': stop_at(), 'last_session': last_session()}
    with open(log, 'a') as f:
        f.write(json.dumps(entry) + '\n')
        f.flush()
        os.fsync(f.fileno())
    return entry


def confirmatory_guard():
    """Fail closed before any GPU work: S, shard and session defined; bundle = frozen commit."""
    if S_REPLICATES not in ('2', '3', '4'):
        raise SystemExit(f'confirmatory: S_REPLICATES must be 2, 3 or 4, got {S_REPLICATES!r}')
    if not FROZEN_COMMIT or CODE_COMMIT != FROZEN_COMMIT:
        raise SystemExit(f'confirmatory: bundle {CODE_COMMIT} is not the frozen commit {FROZEN_COMMIT!r}')
    if len(FREEZE_SHA256) != 64 or len(SCRIPT_SHA256) != 64:
        raise SystemExit('confirmatory: FREEZE_SHA256 and SCRIPT_SHA256 are required')
    if not re.fullmatch(r'[1-9]/[1-9]', SHARD) or int(SHARD[0]) > int(SHARD[2]):
        raise SystemExit(f'confirmatory: SHARD must be i/N, got {SHARD!r}')
    if not SESSION.isdigit() or int(SESSION) < 1:
        raise SystemExit(f'confirmatory: SESSION must be 1, 2, ..., got {SESSION!r}')
    if (SESSION == '1') != (RESUME_SHA256 == ''):
        raise SystemExit('confirmatory: session 1 starts empty; every later session resumes')
    return {'S': int(S_REPLICATES), 'frozen_commit': FROZEN_COMMIT, 'freeze_sha256': FREEZE_SHA256,
            'shard': SHARD, 'session': int(SESSION)}


FREEZE = {}
BUNDLED = ('harness/', 'runner/', 'bank/templates/', 'bank/spec_matrix.csv', 'bank/render.py', 'bank/__init__.py',
           'bank/admission.py', 'twinguard/twinguard_analysis.py', 'twinguard/twinguard_graph.py',
           'notebooks/model_overlay/', 'notebooks/pilot_l4/pilot_l4.py')


def verify_freeze(code):
    """The bundle IS the frozen package: manifest hash = FREEZE_SHA256, S = frozen S, this
    script = the frozen script, and every frozen code/template file in the bundle matches its
    hash, with no extra file under the frozen code directories."""
    mpath = code / 'freeze' / 'manifest.json'
    if sha256(mpath) != FREEZE_SHA256:
        raise RuntimeError('freeze manifest hash differs from FREEZE_SHA256')
    m = json.loads(mpath.read_text())
    if m['design']['S'] != int(S_REPLICATES):
        raise RuntimeError(f"S_REPLICATES {S_REPLICATES} != frozen S {m['design']['S']}")
    if SHARD not in m['design']['shards'] or int(SHARD.split('/')[1]) != len(m['design']['shards']):
        raise RuntimeError(f"shard {SHARD} is not one of the frozen shards {sorted(m['design']['shards'])}")
    frozen = {}
    for files in m['files'].values():
        frozen.update(files)
    for t in m['templates'].values():
        frozen.update(t['files'])
    if frozen.get('notebooks/pilot_l4/pilot_l4.py') != SCRIPT_SHA256:
        raise RuntimeError('this kernel script is not the frozen script')
    bad, missing, extra = [], [], []
    for path, h in frozen.items():
        if not path.startswith(BUNDLED):
            continue
        f = code / path
        if not f.exists():
            missing.append(path)
        elif sha256(f) != h:
            bad.append(path)
    for f in code.rglob('*'):
        rel = f.relative_to(code).as_posix()
        if f.is_file() and rel.startswith(BUNDLED) and rel not in frozen:
            extra.append(rel)
    if bad or missing or extra:
        raise RuntimeError(f'bundle differs from the freeze: bad={bad[:5]} missing={missing[:5]} extra={extra[:5]}')
    FREEZE.update(m)
    return {'freeze_sha256': FREEZE_SHA256, 'frozen_files_checked': len(frozen),
            'deadline_utc': m['confirmatory_deadline_utc']}


def deadline():
    return FREEZE['confirmatory_deadline_epoch']


def stop_at():
    """No run starts after the session margin or after the frozen confirmatory deadline."""
    t = KERNEL_T0 + SESSION_LIMIT_S - STOP_MARGIN_S
    if MODE == 'x1_transfer':
        return min(t, float(X1_STOP_AT_EPOCH), KERNEL_T0 + float(X1_CUTOFF_S))
    if MODE == 'x1_calibration':
        return min(t, KERNEL_T0 + float(X1_CUTOFF_S))
    if MODE in FOLLOWUP_MODES:
        return min(t, float(X3['stop_at_epoch']))
    return min(t, deadline()) if MODE == 'confirmatory' else t


def last_session():
    """This session's stop time is the frozen deadline (logged in sessions.jsonl)."""
    return MODE == 'confirmatory' and deadline() <= KERNEL_T0 + SESSION_LIMIT_S - STOP_MARGIN_S


def deadline_reached():
    """Time alone decides the cut (7.4): close only once the frozen deadline has passed. A
    session that ends earlier (server failure, crash) is resumed by the next session."""
    return MODE == 'confirmatory' and time.time() >= deadline()


def confirmatory_block(code):
    """7.4: the runner schedules 10 sector blocks in the published order (order seed default)
    with interleaved cells; resume skips finished runs; --stop-at defers the rest to the next
    session (a new kernel that attaches this one's sealed archive, RESUME_SHA256)."""
    return run_block(code, 'confirmatory', 'confirmatory', ['--replicates', S_REPLICATES])


def confirmatory_close_out(code):
    """Session reaching the frozen deadline: evaluate finished episodes and give every
    unfinished scheduled run an infra_failed row (7.4 truncation responds to time only).
    CPU only: the runner's close-out never calls the model."""
    return run_block(code, 'confirmatory', 'confirmatory',
                     ['--replicates', S_REPLICATES, '--close-out'])


def shard_status(closed):
    """closed_at_deadline (shard final), complete (every scheduled run has its row), or
    requires_resume (attach this session's sealed archive to session k+1 of the shard)."""
    if closed.get('ok') and 'confirmatory' in R.get('blocks', {}) and deadline_reached():
        return 'closed_at_deadline'
    s = R.get('blocks', {}).get('confirmatory', {}).get('session') or {}
    if s.get('scheduled') and s.get('completed') == s.get('scheduled'):
        return 'complete'
    return 'requires_resume'


def eval_check(code):
    """CPU diagnostic (no model, no study data): the admission patches S+ (safe) and U+
    (weakening) of every template, in every framing, through the SAME isolated evaluation as
    the runs (evaluator uids, read-only oracle copy). Expected: S+ -> W=0, U+ -> W=1, F=1."""
    sys.path.insert(0, str(code))
    from runner.runner import evaluate, outcome
    bank = code / 'bank' / 'templates'
    jobs = [(t.name, kind, f) for t in sorted(bank.iterdir()) if (t / 'template.json').exists()
            for kind in ('s_plus', 'u_plus') for f in ('N', 'P', 'A')]
    expect = {'s_plus': '0', 'u_plus': '1'}
    res, bad = {}, []

    import queue
    slots = queue.Queue()
    for u in EVALS:
        slots.put(u)          # one evaluator uid per concurrent evaluation, as in the runner

    def one(i_job):
        i, (tid, kind, f) = i_job
        user = slots.get()
        try:
            patch = (bank / tid / 'patches' / f'{kind}.diff').read_text()
            ev = evaluate(bank / tid, f, patch, Path('/tmp/wk') / f'ec{i}', user)
            status, W, F, M, crash = outcome({'budget_exhausted': False}, ev)
            shutil.rmtree(Path('/tmp/wk') / f'ec{i}', ignore_errors=True)
            return tid, kind, f, status, W, F, crash
        finally:
            slots.put(user)
    with ThreadPoolExecutor(len(EVALS)) as ex:
        for tid, kind, f, status, W, F, crash in ex.map(one, enumerate(jobs)):
            key = f'{kind} W={W} F={F} crash={crash} status={status}'
            res[key] = res.get(key, 0) + 1
            if str(W) != expect[kind] or str(F) != '1':
                bad.append(f'{tid} {kind} {f} W={W} F={F} crash={crash} status={status}')
    return {'evaluations': len(jobs), 'counts': res, 'unexpected': bad[:60],
            'n_unexpected': len(bad)}


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



# ------------------------------------------------------------------ D15 follow-up (x3, Colab)
X3 = {}
X3_OWN = {f'followup/{k}_manifest.json{e}' for k in FOLLOWUP_MODES for e in ('', '.sha256', '.ots')}


def x3_verify(code):
    """The bundle is the sealed D15 package (manifest hash, this script, every listed file with
    its hash, no extra file); the session chain is well formed (1 starts empty, k resumes)."""
    mpath = code / FOLLOWUP_MANIFEST[MODE]
    if not mpath.exists() or sha256(mpath) != X3_MANIFEST_SHA256:
        raise RuntimeError(f'{MODE} manifest missing or its hash differs from X3_MANIFEST_SHA256')
    m = json.loads(mpath.read_text())
    X3.update(m)
    if m['files'].get('notebooks/pilot_l4/pilot_l4.py') != SCRIPT_SHA256:
        raise RuntimeError('this kernel script is not the D15 script')
    have = {f.relative_to(code).as_posix() for f in code.rglob('*') if f.is_file()} - X3_OWN
    bad = sorted(p for p in have & set(m['files']) if sha256(code / p) != m['files'][p])
    missing = sorted(set(m['files']) - have)
    extra = sorted(have - set(m['files']))
    if bad or missing or extra:
        raise RuntimeError(f'bundle differs from the D15 manifest: bad={bad[:5]} '
                           f'missing={missing[:5]} extra={extra[:5]}')
    if not SESSION.isdigit() or int(SESSION) < 1:
        raise RuntimeError(f'x3: SESSION must be 1, 2, ..., got {SESSION!r}')
    if (SESSION == '1') != (RESUME_SHA256 == ''):
        raise RuntimeError('x3: session 1 starts empty; every later session resumes')
    if SHARD:
        raise RuntimeError('x3 has no shards')
    names = [b['name'] for b in m['blocks']]
    if not names or not names[0].endswith('_main') or m['blocks'][0]['start_by_epoch'] is not None \
            or len(set(names)) != len(names) or m.get('mode', 'x3') != MODE:
        raise RuntimeError('x3 manifest: the main block comes first and has no start_by')
    return {'files': len(m['files']), 'session': int(SESSION),
            'stop_at_epoch': m['stop_at_epoch'], 'blocks': names}


def x3_chain(restored):
    """Session k resumes exactly session k - 1 of this seal; each session appends its entry
    (with the parent's seal kind: a periodic snapshot may have lost later events, re-run)."""
    log = RESULTS_DIR / 'x3_sessions.jsonl'
    k = int(SESSION)
    if k == 1:
        if (RESULTS_DIR / x3_blocks()[0]['name']).exists() or log.exists():
            raise RuntimeError('session 1 must start without x3 results')
    else:
        if not log.exists():
            raise RuntimeError('resumed archive has no x3 session log')
        prev = json.loads(log.read_text().strip().splitlines()[-1])
        if (prev['session'], prev['manifest_sha256']) != (k - 1, X3_MANIFEST_SHA256):
            raise RuntimeError(f'x3 resume chain broken: previous entry {prev}, this session {k}')
    entry = {'session': k, 'manifest_sha256': X3_MANIFEST_SHA256, 'code_commit': CODE_COMMIT,
             'parent_sha256': RESUME_SHA256 or None, 'parent_seal': restored.get('parent_seal'),
             'started_utc': KERNEL_T0, 'stop_at': stop_at()}
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(log, 'a') as f:
        f.write(json.dumps(entry) + '\n')
        f.flush()
        os.fsync(f.fileno())
    return entry


def x3_blocks():
    """The sealed blocks, in their sealed order: the main block, then the descriptive ones."""
    return X3['blocks']


def x3_spec(name):
    return next(b for b in x3_blocks() if b['name'] == name)


def x3_args(code, name):
    b = x3_spec(name)
    a = ['--bank', str(code / 'followup' / 'bank_x3' / 'templates'),
         '--spec', str(code / b['spec']), '--replicates', '1']
    return a + (['--framings', ','.join(b['framings'])] if b['framings'] != ['N', 'P', 'A'] else [])


def block_complete(name):
    s = (R.get('blocks', {}).get(name) or {}).get('session') or {}
    return bool(s.get('scheduled')) and s.get('completed') == s.get('scheduled')


def first_start_utc(name):
    """utc of the block's first 'start' event (the runner creates the directory and manifest
    even when the stop time leaves every run unstarted), or None."""
    f = RESULTS_DIR / name / 'attempts.jsonl'
    if not f.exists():
        return None
    for line in f.read_text(errors='replace').splitlines():
        try:
            ev = json.loads(line)
        except Exception:
            continue
        if ev.get('event') == 'start':
            return float(ev.get('utc') or 0)
    return None


def block_started(name):
    return first_start_utc(name) is not None


def x3_may_start(i):
    """Sealed start rule (time only, never results): block i > 0 may START only once every
    earlier block has a row for each of its runs, and before its start_by; once started (in this
    or an earlier session) it continues until the stop time."""
    bl = x3_blocks()
    b = bl[i]
    if time.time() >= stop_at() or not all(block_complete(p['name']) for p in bl[:i]):
        return False
    return block_started(b['name']) or b['start_by_epoch'] is None or \
        time.time() < float(b['start_by_epoch'])


def x3_m3_may_run():          # kept for the tests and the D15 text: the M3 ablation's rule
    return x3_may_start(next(i for i, b in enumerate(x3_blocks()) if b['name'] == 'x3_m3'))


def x3_run(code, b):
    """A block that has not started is first launched with the runner's --stop-at at its
    start_by (the runner starts no run after it: the race of Astra/Sol); once it has started, it
    runs on until the session stop time."""
    name = b['name']
    if b['start_by_epoch'] is None or block_started(name):
        return run_block(code, 'x3', name, x3_args(code, name))
    first = run_block(code, 'x3', name, x3_args(code, name)
                      + ['--stop-at', str(min(stop_at(), float(b['start_by_epoch'])))])
    if not block_started(name) or block_complete(name):
        return {'first_launch': first}
    return {'first_launch': first, 'continued': run_block(code, 'x3', name, x3_args(code, name))}


def x3_block(code):
    res = {}
    for i, b in enumerate(x3_blocks()):
        rule = {'may_start': x3_may_start(i), 'started_before': block_started(b['name']),
                'now_epoch': time.time(), 'start_by_epoch': b['start_by_epoch']}
        res[b['name']] = {'rule': rule}
        if not rule['may_start']:
            break
        res[b['name']]['run'] = x3_run(code, b)
        if not block_complete(b['name']):
            break
    return res


# ------------------------------------------------------------------ D17 ladder (Colab)
class IsolationBreach(RuntimeError):
    """The model server is reachable by an agent/evaluator uid: the session must end."""


def ladder_dests():
    return [Path(MODEL_SPECS[k]['dest']) for k in LADDER_KINDS]


def block_done(name):
    """Every scheduled run of the block has a row (this session or a resumed one)."""
    f = RESULTS_DIR / name / 'runs.csv'
    if not f.exists():
        return False
    import csv as _csv
    have = {r['run_id'] for r in _csv.DictReader(open(f, newline=''))}
    return len(have) >= int(x3_spec(name)['runs'])


def startup_failed(name):
    return (RESULTS_DIR / name / 'startup_failed.json').exists()


def ladder_may_start(i):
    """Sealed order (time only, never results): block i may start only once every earlier block
    has a row for each run or a recorded start-up failure, and before the stop time."""
    bl = x3_blocks()
    return time.time() < stop_at() and all(block_done(p['name']) or startup_failed(p['name'])
                                           for p in bl[:i])


LADDER_LOG = 'ladder_serve.jsonl'    # sealed in results/: every start, its arguments, toy check
TOY_DIR = UDS_DIR / 'toy'           # root-only, outside the sealed results (never analysed)
TOY_RULE = ('6 toy episodes (tests/fixtures/tpl_m1, never the bank): all 6 with a row that is not '
            'infra_failed, and at least one with tool_calls >= 1; repair quality is never judged')


def ladder_log(rec):
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_DIR / LADDER_LOG, 'a') as f:
        f.write(json.dumps(rec, default=str) + '\n')
        f.flush()
        os.fsync(f.fileno())


def ladder_toy(code, kind):
    """Sealed technical check before the bank (Astra): generation and tool calls work."""
    spec = UDS_DIR / 'fixture_spec.csv'
    fb = UDS_DIR / 'fixture_bank'
    fb.mkdir(parents=True, exist_ok=True)
    dst = fb / 'FIXTURE.m1_toy'
    if not dst.exists():
        shutil.copytree(code / 'tests' / 'fixtures' / 'tpl_m1', dst)
        m = json.loads((dst / 'template.json').read_text())
        m['issue_paraphrases'] = [m['problem_statement']] * 4
        (dst / 'template.json').write_text(json.dumps(m))
    spec.write_text('template_id,split,family,mechanism\nFIXTURE.m1_toy,pilot,logistics,M1\n')
    TOY_DIR.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(TOY_DIR / kind, ignore_errors=True)
    run = run_block(code, 'runner_smoke', kind,
                    ['--bank', str(fb), '--spec', str(spec), '--limit', '6', '--replicates', '1'],
                    out_root=TOY_DIR)
    import csv as _csv
    f = TOY_DIR / kind / 'runs.csv'
    rows = list(_csv.DictReader(open(f, newline=''))) if f.exists() else []
    tools = [int(float(r.get('tool_calls') or 0)) for r in rows]
    out = {'rule': TOY_RULE, 'rows': len(rows),
           'status_counts': {x: sum(r['status'] == x for r in rows) for x in {r['status'] for r in rows}},
           'episodes_with_tool_calls': sum(t >= 1 for t in tools), 'runner_rc': run.get('rc')}
    out['ok'] = len(rows) == 6 and not any(r['status'] == 'infra_failed' for r in rows) \
        and out['episodes_with_tool_calls'] >= 1
    return out


def ladder_serve(kind, procs):
    """Stop the previous server; serve `kind` from its pinned HF files (hash-checked) on the
    root-only socket, with the study's two start attempts; re-check that no agent/evaluator uid
    can reach it. A failed isolation check raises IsolationBreach (the session ends)."""
    global LADDER_KIND, MODEL
    stop(procs)
    procs.clear()
    LADDER_KIND = kind
    MODEL = model_path()
    R['model_path'] = str(MODEL)
    h = model_hash_check()
    if not h.get('all_match'):
        raise RuntimeError(f"served files do not match HF {model_spec()['revision'][:7]}: {h}")
    R['verified_revision'] = model_spec()['revision']
    errs = []
    for extra in ((), ('--max-num-seqs', '32')):
        try:
            p, secs, ex = start_server(1, '0', 8000, f'{kind}_8000', ('--uds', str(UDS), *extra))
            procs.append(p)
            break
        except Exception as e:
            errs.append({'extra': list(extra), 'error': f'{type(e).__name__}: {e}'[-1500:]})
    else:
        raise RuntimeError(json.dumps(errs)[-3000:])
    R['served_model'] = SERVED[8000]
    if SERVED[8000] != str(MODEL):
        raise RuntimeError(f'served id {SERVED[8000]!r} is not the model path {str(MODEL)!r}')
    u = server_unreachable()
    if not u.get('ok'):
        raise IsolationBreach(f'server reachable by an agent/evaluator uid: {u}')
    rec = {'model': kind, 'revision': model_spec()['revision'], 'utc': time.time(),
           'load_seconds': secs, 'extra_args': ex, 'start_errors': errs,
           'vllm_budget': R.get('colab_vllm_budget'), 'max_model_len': 32768,
           'concurrency': len(AGENTS)}
    try:
        rec['kv'] = kv_info(f'{kind}_8000')
    except Exception as exc:
        rec['kv'] = f'{type(exc).__name__}: {exc}'
    rec['toy'] = ladder_toy(code_dir(), kind)
    ladder_log(rec)
    if not rec['toy']['ok']:
        raise RuntimeError(f"toy check failed: {rec['toy']}")
    return {'hashes': h, **rec, 'unreachable': u}


def ladder_block(code, procs):
    """D17: the sealed blocks in order, one model server at a time. A model whose files or
    server fail (never one already started in an earlier session) is recorded as
    startup_failed in its block directory and the next block may start."""
    res = {}
    for i, b in enumerate(x3_blocks()):
        name = b['name']
        rule = {'may_start': ladder_may_start(i), 'started_before': block_started(name),
                'now_epoch': time.time()}
        res[name] = {'rule': rule}
        if block_done(name) or startup_failed(name):
            res[name]['skipped'] = 'done' if block_done(name) else 'startup_failed'
            continue
        if not rule['may_start']:
            break
        try:
            res[name]['serve'] = ladder_serve(b['model'], procs)
        except IsolationBreach:
            raise
        except Exception as exc:
            if block_started(name):
                raise                     # a started block is resumed, never declared failed
            rec = {'block': name, 'model': b['model'], 'revision': b['revision'],
                   'utc': time.time(), 'error': redact(f'{type(exc).__name__}: {exc}')[-3000:]}
            (RESULTS_DIR / name).mkdir(parents=True, exist_ok=True)
            (RESULTS_DIR / name / 'startup_failed.json').write_text(json.dumps(rec, indent=1))
            res[name]['startup_failed'] = rec
            continue
        res[name]['run'] = run_block(code, 'x3', name, x3_args(code, name))
        if not block_done(name):
            break
    stop(procs)
    procs.clear()
    return res


def ladder_status(closed):
    if not closed.get('ok'):
        return 'close_out_failed'
    if x3_deadline_reached() or closed.get('ran'):
        return 'closed_at_deadline' if closed.get('ran') else 'requires_close_out'
    if all(block_done(b['name']) or startup_failed(b['name']) for b in x3_blocks()):
        return 'complete'
    return 'requires_resume'


def x3_deadline_reached():
    return MODE in FOLLOWUP_MODES and bool(X3) and time.time() >= float(X3['stop_at_epoch'])


def x3_close_out(code):
    """Past the sealed stop time: evaluate finished episodes and give every unfinished scheduled
    run of a STARTED block an infra_failed row (time cut; CPU only, the model is never called).
    A block that never started is not closed out (the main block always is)."""
    out = {}
    for i, b in enumerate(x3_blocks()):
        if (i == 0 and MODE != 'ladder') or block_started(b['name']):
            out[b['name']] = run_block(code, 'x3', b['name'],
                                       x3_args(code, b['name']) + ['--close-out'])
    return out


def x3_status(closed):
    """complete, closed_at_deadline, close_out_failed, requires_close_out (past the stop time
    without a successful close-out in this session: one more session closes out), or
    requires_resume (attach this session's sealed archive to session k + 1 with RESUME_SHA256).
    Read BEFORE the seal."""
    if MODE == 'ladder':
        return ladder_status(closed)
    if not closed.get('ok'):
        return 'close_out_failed'
    if x3_deadline_reached() or closed.get('ran'):
        return 'closed_at_deadline' if closed.get('ran') else 'requires_close_out'
    for i, b in enumerate(x3_blocks()):
        if block_started(b['name']) or i == 0:
            if not block_complete(b['name']):
                return 'requires_resume'
        elif all(block_complete(p['name']) for p in x3_blocks()[:i]) and \
                time.time() < float(b['start_by_epoch']):
            return 'requires_resume'      # still allowed to start (in the next session)
        else:
            break                     # this block can no longer start: neither can later ones
    return 'complete'


# ------------------------------------------------------------------ Colab (smoke and D15 x3)
# Colab has internet and no Kaggle image: the notebook (notebooks/colab/) downloads the official
# wheelhouse and the Kaggle model into /kaggle/input with the author's credentials, places this
# script in /kaggle/src and removes the credentials before launching it. The script then
# installs the Kaggle package versions and the wheelhouse, runs the runner (and so every agent
# and evaluator) in an empty network namespace, and refuses any mode but COLAB_MODES.
# The Kaggle environment (probe of the pinned image 37c64f7d after the kernels' wheelhouse
# install): kaggle_freeze.txt is its `pip freeze --all`; lock_base.txt is the part of it the
# wheelhouse and the evaluator need (pip-tools style, hashed), every version as on Kaggle.
COLAB_ENV = Path('notebooks') / 'colab' / 'kaggle_env'
COLAB_TORCH_INDEX = 'https://download.pytorch.org/whl/cu128'
# the runner (so every agent and evaluator) and every isolation probe start in fresh network AND
# System V IPC namespaces; files, pathname sockets and /dev/shm stay governed by uid permissions,
# probed in 8_isolation (the boundary is declared in D15)
COLAB_NETNS = ['unshare', '--net', '--ipc', '--']
# connect probe run as an agent uid inside the namespace: exit 0 = connected, 3 = unreachable
# (ENETUNREACH / EHOSTUNREACH / EADDRNOTAVAIL), 4 = any other error. Only 3 counts as denied.
COLAB_NET_PROBE = ("import errno, socket, sys\n"
                   "try:\n    socket.create_connection((sys.argv[1], int(sys.argv[2])), 3)\n"
                   "except OSError as e:\n"
                   "    sys.exit(3 if e.errno in (errno.ENETUNREACH, errno.EHOSTUNREACH, "
                   "errno.EADDRNOTAVAIL) else 4)\n"
                   "sys.exit(0)\n")
COLAB_EXPECTED = '0.19.1 2.10.0+cu128 5.13.1'      # vllm torch transformers, as on Kaggle
# imported after the install (smoke 3: vLLM's server imports uvloop, which no package declares):
# a missing runtime import fails the install with the full list, before any model or server
COLAB_IMPORT_PROBE = ('vllm.entrypoints.openai.api_server', 'uvicorn.loops.uvloop',
                      'uvicorn.protocols.http.httptools_impl', 'adk_submission')
COLAB_IMPORT_CODE = ('import importlib, sys\nbad = []\nfor m in sys.argv[1:]:\n    try:\n'
                     '        importlib.import_module(m)\n    except Exception as e:\n'
                     "        bad.append(f'{m}: {type(e).__name__}: {e}')\n"
                     "print('\\n'.join(bad))\nsys.exit(1 if bad else 0)\n")
# credential-like argument names (`--NotebookApp.token X`, `--token=X`, `KAGGLE_KEY=X`, `?token=X`);
# `--max-num-batched-tokens` or `--thinking-token-budget` are not credentials
COLAB_SECRET_SCAN = r'''
import glob, re
NAME = re.compile(r'(?i)(^|[._?&-])(token|key|api[_-]?key|password|passwd|secret|kaggle_username)$')
bad = set()
for c in glob.glob('/proc/[0-9]*/cmdline'):
    try:
        a = [x.decode('utf-8', 'replace') for x in open(c, 'rb').read().split(b'\0') if x]
    except OSError:
        continue
    for i, x in enumerate(a):
        k, eq, v = x.partition('=')
        if NAME.search(k.lstrip('-')):
            val = v if eq else (a[i + 1] if i + 1 < len(a) and not a[i + 1].startswith('-') else '')
            if val.strip():
                bad.add(c.split('/')[2])
        for seg in re.split(r'[?&;]', x)[1:]:          # every URL / query parameter
            k2, eq2, v2 = seg.partition('=')
            if eq2 and v2.strip() and NAME.search(k2):
                bad.add(c.split('/')[2])
print('SCAN_OK ' + ' '.join(sorted(bad, key=int)))
'''
COLAB_DENIED = {'content_ls': 'ls /content', 'content_drive_ls': 'ls /content/drive',
                'net_lo_tcp': f"{sys.executable} -c \"import socket;socket.create_connection(('127.0.0.1',8080),3)\"",
                'net_tcp_ext': f"{sys.executable} -c \"import socket;socket.create_connection(('8.8.8.8',53),3)\"",
                'net_dns_https': f"{sys.executable} -c \"import socket;socket.create_connection(('pypi.org',443),3)\"",
                'net_metadata': f"{sys.executable} -c \"import socket;socket.create_connection(('169.254.169.254',80),3)\""}


def kaggle_wheel_hashes(freeze):
    """{wheel file name: sha256} of the wheelhouse install recorded in the Kaggle freeze."""
    out = {}
    for line in freeze.splitlines():
        m = re.match(r'\S+ @ file:///tmp/wheelhouse/(\S+?)#sha256=([0-9a-f]{64})$', line.strip())
        if m:
            out[m.group(1)] = m.group(2)
    return out


def freeze_lines(text):
    """{(name, version or installed file name)} from `pip freeze`, without pip itself (seeded by
    the venv); `name @ file:///.../f.whl#sha256=..` compares by the file name only (hashes are
    checked on the files themselves)."""
    out = set()
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if ' @ ' in line:
            name, url = line.split(' @ ', 1)
            val = url.split('#', 1)[0].rsplit('/', 1)[-1]
        elif '==' in line:
            name, val = line.split('==', 1)
        else:
            name, val = line, ''
        name = re.sub(r'[-_.]+', '-', name.strip()).lower()
        if name != 'pip':
            out.add((name, val.strip()))
    return out


def colab_install():
    """As on Kaggle: (1) the image's packages at Kaggle's versions (lock_base.txt, hash-checked,
    --no-deps), then (2) the wheelhouse files with --no-deps --force-reinstall, exactly the
    files the Kaggle install recorded. The resulting freeze must be a subset of Kaggle's."""
    if sys.version_info[:2] != (3, 12):
        raise RuntimeError(f'the wheelhouse is cp312; this interpreter is {sys.version}')
    env = code_dir() / COLAB_ENV
    if not all((env / f).is_file() for f in ('kaggle_freeze.txt', 'lock_base.txt')):
        raise FileNotFoundError(f'{COLAB_ENV} not in the code bundle (build with PLATFORM=colab)')
    kaggle = (env / 'kaggle_freeze.txt').read_text()
    logs = Path('/kaggle/working/install')
    logs.mkdir(parents=True, exist_ok=True)
    whl = sorted(glob.glob('/kaggle/input/**/gemma-4-developer-agent-wheelhouse/**/*.whl',
                           recursive=True))
    if not whl:
        raise FileNotFoundError('wheelhouse not downloaded into /kaggle/input')
    tmp = Path('/tmp/wheelhouse'); tmp.mkdir(exist_ok=True)
    for w in map(Path, whl):
        if 'cutlass' in w.name.lower():
            continue
        name = w.name.replace('cu128', '+cu128') if ('cu128' in w.name and '+' not in w.name) else w.name
        if not (tmp / name).exists():
            os.symlink(w, tmp / name)
    wheels = sorted(str(w) for w in tmp.glob('*.whl'))
    got = {Path(w).name: hashlib.sha256(Path(w).read_bytes()).hexdigest() for w in wheels}
    if got != kaggle_wheel_hashes(kaggle):
        raise RuntimeError('wheelhouse files differ from the ones installed on Kaggle')
    def step(tag, cmd):
        r = subprocess.run(cmd, capture_output=True, text=True)
        (logs / f'{tag}.log').write_text(f'$ {cmd}\n{r.stdout}\n--- stderr\n{r.stderr}\nrc={r.returncode}\n')
        if r.returncode:
            raise RuntimeError(f'{tag} failed:\n' + (r.stdout + r.stderr)[-4000:])
        return r.stdout
    step('1_lock', [sys.executable, '-m', 'pip', 'install', '--no-deps', '--require-hashes',
                    '--extra-index-url', COLAB_TORCH_INDEX, '-r', str(env / 'lock_base.txt')])
    step('2_wheelhouse', [sys.executable, '-m', 'pip', 'install', '--no-deps', '--force-reinstall',
                          *wheels])
    ver = sh(f'{sys.executable} -c "import vllm,torch,transformers;print(vllm.__version__,torch.__version__,transformers.__version__)"')
    freeze = step('3_freeze', [sys.executable, '-m', 'pip', 'freeze', '--all']).strip()
    Path('/kaggle/working/pip_freeze.txt').write_text(freeze + '\n')     # open output, synced
    names = {n for n, _ in freeze_lines(freeze)}
    missing = sorted({'vllm', 'torch', 'transformers', 'numpy', 'pandas', 'pytest', 'adk-submission'} - names)
    if missing:
        raise RuntimeError(f'freeze lacks required packages: {missing}')
    not_kaggle = sorted(freeze_lines(freeze) - freeze_lines(kaggle))
    try:                                                   # diagnostics only, never gate
        chk = subprocess.run([sys.executable, '-m', 'pip', 'check'], capture_output=True, text=True)
        (logs / 'pip_check.log').write_text(chk.stdout + chk.stderr)
    except Exception:                                      # noqa: BLE001
        pass
    diag = sh(f'{sys.executable} -c "import torch,platform;print(torch.version.cuda, '
              f'torch.backends.cudnn.version(), platform.libc_ver())"')
    out = {'python': sys.version, 'n_wheels': len(wheels), 'vllm_torch_transformers': ver,
           'versions_as_kaggle': ver == COLAB_EXPECTED, 'not_as_on_kaggle': not_kaggle,
           'n_packages': len(freeze_lines(freeze)),
           'pip_freeze_sha256': hashlib.sha256(freeze.encode()).hexdigest(),
           'kaggle_freeze_sha256': hashlib.sha256(kaggle.encode()).hexdigest(),
           'lock_sha256': hashlib.sha256((env / 'lock_base.txt').read_bytes()).hexdigest(),
           'pip': sh(f'{sys.executable} -m pip --version'), 'uv': sh('uv --version'),
           'torch_cuda_cudnn_libc': diag, 'nvcc': sh('nvcc --version | tail -1'),
           'driver': sh('nvidia-smi --query-gpu=driver_version --format=csv,noheader')}
    if not out['versions_as_kaggle']:
        raise RuntimeError(f'package versions differ from the Kaggle serving stack: {ver!r}')
    if not_kaggle:
        raise RuntimeError(f'packages not as on Kaggle: {not_kaggle[:20]}')
    step('4_imports', [sys.executable, '-c', COLAB_IMPORT_CODE, *COLAB_IMPORT_PROBE])
    out['imports_ok'] = list(COLAB_IMPORT_PROBE)
    return out


def colab_net_probe_cmd(host, port):
    """COLAB_NET_PROBE as one shell-safe command (base64: it passes two shell layers)."""
    import base64
    code = base64.b64encode(COLAB_NET_PROBE.encode()).decode()
    return (f'{sys.executable} -I -c "import base64;exec(base64.b64decode(\'{code}\'))" '
            f'{host} {int(port)}')


def colab_netns_check():
    """Colab has internet and local services (Jupyter and others) and no usable netfilter
    (iptables is refused even to root). Isolation is a fresh network namespace instead: the
    runner and all its children (agents, evaluators) run in one (runner_cmd), and every
    isolation probe runs in one too (as_user). Checked here: inside a new namespace only a
    down loopback exists (read over netlink inside the namespace, not from the inherited /sys)
    and, as an agent uid, external, metadata and loopback connections fail as unreachable (any
    other outcome, a refusal or an error, counts as not denied). Fail closed."""
    ns = ' '.join(COLAB_NETNS)
    links = sh(f"{ns} cat /proc/net/dev | tail -n +3 | cut -d: -f1 | tr -d ' '").split()
    ip = sh(f'{ns} ip -o link show').strip().splitlines()
    up = [l for l in ip if 'state DOWN' not in l or ',UP' in l.split('>')[0]]
    if links != ['lo'] or len(ip) != 1 or ': lo:' not in ip[0] or up:
        raise RuntimeError(f'network namespace not empty: links={links} ip={ip}')
    rcs = {f'{h}:{port}': as_user(AGENTS[0], colab_net_probe_cmd(h, port))
           for h, port in (('8.8.8.8', 53), ('169.254.169.254', 80), ('127.0.0.1', 8080))}
    reach = {k: rc for k, rc in rcs.items() if rc != '3'}
    if reach:
        raise RuntimeError(f'agent uid not denied the network inside the namespace: {reach}')
    return {'method': 'netns+ipc (' + ns + ')', 'links': links, 'ip_link': ip, 'probe_rc': rcs}


def colab_hide():
    """/content (Colab's working dir) closed; /proc mounted with hidepid=2 when the runtime
    allows it (recorded). Either way no command line VISIBLE TO AN AGENT OR EVALUATOR uid may
    carry a non-empty credential-like argument (scanned as those uids; abort otherwise)."""
    out = {'content': sh('chmod 0700 /content 2>/dev/null; stat -c %a /content')}
    out['hidepid_rc'] = sh('mount -o remount,rw,hidepid=2 /proc >/dev/null 2>&1; echo $?')
    leaks = {}
    for u in (AGENTS[0], EVALS[0]):
        r = subprocess.run(['setpriv', f'--reuid={u}', f'--regid={u}', '--clear-groups',
                            '--no-new-privs', '--', sys.executable, '-I', '-c', COLAB_SECRET_SCAN],
                           capture_output=True, text=True)
        words = r.stdout.split()
        if r.returncode != 0 or not words or words[0] != 'SCAN_OK':   # the scan must run
            raise RuntimeError(f'credential scan failed as {u}: rc={r.returncode} {r.stderr[-300:]}')
        if words[1:]:
            leaks[u] = words[1:]
    out['cmdline_secret_pids'] = leaks
    if leaks:
        raise RuntimeError(f'process command lines carry credentials or tokens: {leaks}')
    return out


UNIX_TYPES = {1: 'SOCK_STREAM', 2: 'SOCK_DGRAM', 5: 'SOCK_SEQPACKET'}


def colab_unix_reach(typed):
    """Colab: every Unix socket (path AND abstract; abstract ones have no file permissions)
    probed with its own type by an agent and an evaluator uid; any connect succeeds -> abort."""
    reach = []
    for name, t in sorted(typed):
        kind = UNIX_TYPES.get(t, 'SOCK_STREAM')
        addr = repr('\0' + name[1:]) if name.startswith('@') else repr(name)
        probe = (f"{sys.executable} -I -c \"import socket;s=socket.socket(socket.AF_UNIX,"
                 f"socket.{kind});s.settimeout(2);s.connect({addr})\"")
        for u in (AGENTS[0], EVALS[0]):
            if as_user(u, probe) == '0':
                reach.append(f'{u}:{name}:{kind}')
    return reach


def uds_chat(body, timeout=900):
    st, raw = uds_request('POST', '/v1/chat/completions',
                          {'model': SERVED.get(8000, 'gemma'), **body}, timeout=timeout)
    return json.loads(raw) if st == 200 else {'http_error': st, 'body': raw[:1500].decode(errors='replace')}


def colab_capacity(tag, srv=None):
    """KV capacity, memory (sampled under load) and throughput at concurrency 1/4/8 through the
    root-only socket. Every request must succeed; errors are recorded; preemptions are counted
    in the live server log."""
    def refresh():
        log = getattr(srv, 'log_path', None)
        if log and Path(log).exists():
            shutil.copyfile(log, f'/kaggle/working/vllm_{tag}.log')
    refresh()
    msgs = long_prompt()
    q = 'nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader'
    res = {'kv': kv_info(tag), 'gpu_mem_idle': sh(q)}
    for conc in (1, 4, 8):
        n = max(4, conc * 2)
        body = {'messages': msgs, 'max_tokens': 1024, 'seed': 3, **SAMPLING,
                'chat_template_kwargs': {'enable_thinking': True}}
        mem, done = [], threading.Event()

        def sample():
            while not done.wait(2):
                mem.append(sh(q))
        th = threading.Thread(target=sample, daemon=True)
        th.start()
        t0 = time.time()

        def one(i):
            a = time.time()
            try:
                r = uds_chat(body)
            except Exception as exc:
                r = {'error': f'{type(exc).__name__}: {exc}'[:500]}
            return a, r, time.time()
        with ThreadPoolExecutor(conc) as ex:
            outs = list(ex.map(one, range(n)))
        wall = time.time() - t0
        done.set()
        th.join(5)
        ok = [o for o in outs if 'choices' in o[1]]
        comp = sum(o[1]['usage']['completion_tokens'] for o in ok)
        res[f'conc_{conc}'] = {'requests': n, 'ok': len(ok), 'wall_s': round(wall, 1),
                               'completion_tok_per_s': round(comp / wall, 1),
                               'mean_latency_s': round(sum(o[2] - o[0] for o in ok) / max(1, len(ok)), 1),
                               'errors': [o[1] for o in outs if 'choices' not in o[1]][:3],
                               'gpu_mem_peak_mib': max((int(m.split()[0]) for m in mem
                                                         if m.split() and m.split()[0].isdigit()),
                                                        default=None)}
        R['colab_capacity_partial'] = res            # kept even when this phase fails
        save()
        if len(ok) != n:
            raise RuntimeError(f'capacity: {n - len(ok)} of {n} requests failed at concurrency {conc}')
    refresh()
    log = Path(f'/kaggle/working/vllm_{tag}.log').read_text(errors='replace')
    res['preemption_lines'] = sum('preempt' in l.lower() for l in log.splitlines())
    return res


# ------------------------------------------------------------------ D12 exploratory (x1)
X1 = {}


def x1_verify(code):
    """The bundle is the sealed D12 package: x1 manifest hash, this script, and every listed
    file with its hash; transfer: the rung equals the sealed selection attached as input."""
    mpath = code / 'explore' / 'x1_manifest.json'
    if sha256(mpath) != X1_MANIFEST_SHA256:
        raise RuntimeError('x1 manifest hash differs from X1_MANIFEST_SHA256')
    m = json.loads(mpath.read_text())
    X1.update(m)
    if m['files'].get('notebooks/pilot_l4/pilot_l4.py') != SCRIPT_SHA256:
        raise RuntimeError('this kernel script is not the D12 script')
    own = {'explore/x1_manifest.json', 'explore/x1_manifest.json.sha256', 'explore/x1_manifest.json.ots'}
    have = {f.relative_to(code).as_posix() for f in code.rglob('*') if f.is_file()} - own
    bad = sorted(p for p in have & set(m['files']) if sha256(code / p) != m['files'][p])
    missing = sorted(set(m['files']) - have)
    extra = sorted(have - set(m['files']))
    if bad or missing or extra:
        raise RuntimeError(f'bundle differs from the D12 manifest: bad={bad[:5]} '
                           f'missing={missing[:5]} extra={extra[:5]}')
    b = m['budget']
    try:
        cutoff, hard = float(X1_CUTOFF_S), float(X1_HARD_S)
    except ValueError:
        raise RuntimeError(f'X1_CUTOFF_S/X1_HARD_S must be numbers: {X1_CUTOFF_S!r} {X1_HARD_S!r}')
    limit = b['calibration_hard_s'] if MODE == 'x1_calibration' else b['transfer_hard_s_max']
    try:
        session = float(X1_SESSION_S)
    except ValueError:
        raise RuntimeError(f'X1_SESSION_S must be a number, got {X1_SESSION_S!r}')
    if session != hard + b['session_overhead_s']:
        raise RuntimeError(f'X1_SESSION_S {session} != X1_HARD_S + {b["session_overhead_s"]}')
    if not 0 < hard <= limit or cutoff != hard - b['start_margin_s'] or cutoff <= 0:
        raise RuntimeError(f'X1_HARD_S {hard} / X1_CUTOFF_S {cutoff} disagree with the sealed '
                           f'budget for {MODE} (hard <= {limit}, cutoff = hard - {b["start_margin_s"]})')
    out = {'files': len(m['files']), 'mode': MODE, 'cutoff_s': cutoff, 'hard_s': hard}
    if MODE == 'x1_calibration' and (SHARD or X1_RUNG or X1_SELECTION_SHA256):
        raise RuntimeError('x1_calibration takes no SHARD, X1_RUNG or X1_SELECTION_SHA256')
    if MODE == 'x1_transfer':
        if X1_RUNG not in ('L1', 'L2', 'L3'):
            raise RuntimeError(f'X1_RUNG must be L1, L2 or L3, got {X1_RUNG!r}')
        shards = [f"{i}/{m['transfer']['shards']}" for i in range(1, m['transfer']['shards'] + 1)]
        if SHARD not in shards:
            raise RuntimeError(f'SHARD {SHARD!r} is not one of the sealed shards {shards}')
        if str(X1_STOP_AT_EPOCH) != str(m['transfer']['stop_at_epoch']):
            raise RuntimeError(f"X1_STOP_AT_EPOCH {X1_STOP_AT_EPOCH!r} != sealed {m['transfer']['stop_at_epoch']}")
        sel = [p for p in glob.glob('/kaggle/input/**/x1_selection.json', recursive=True)
               if sha256(p) == X1_SELECTION_SHA256]
        if len(sel) != 1:
            raise RuntimeError('expected exactly one attached x1_selection.json with X1_SELECTION_SHA256')
        chosen = json.loads(Path(sel[0]).read_text()).get('selected')
        if chosen != X1_RUNG:
            raise RuntimeError(f'X1_RUNG {X1_RUNG!r} is not the sealed selection {chosen!r}')
        out.update({'rung': X1_RUNG, 'shard': SHARD, 'stop_at': float(X1_STOP_AT_EPOCH)})
    return out


def x1_watchdog():
    """Absolute session deadline for the x1 modes, from the very start: whatever is running
    (set-up, runner, close-out, checkpoint, seal), the process ends at KERNEL_T0 +
    X1_SESSION_S. The periodic sealed archive is replaced atomically, so the last complete
    checkpoint survives; the results JSON records the event first."""
    end = KERNEL_T0 + float(X1_SESSION_S)

    def run():
        while time.time() < end:
            time.sleep(min(5.0, max(0.1, end - time.time())))
        try:
            R['x1_watchdog'] = {'fired_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
            for u in AGENTS + EVALS:
                sh(f'pkill -9 -u {u}')
            with TMP_LOCK:            # no snapshot can create or publish an archive after this
                CLOSING.set()
                for tmp in set(OPEN_TMPS) | set(glob.glob('/kaggle/working/.sealed_*.tmp')):
                    Path(tmp).unlink(missing_ok=True)      # a seal cut half-way
            save()
        finally:
            os._exit(3)
    th = threading.Thread(target=run, daemon=True)
    th.start()
    return th


def x1_args(code):
    x = code / 'explore' / 'bank_x1'
    if MODE == 'x1_calibration':
        return 'x1_calibration', ['--bank', str(x / 'templates'), '--spec',
                                  str(x / 'spec_calibration.csv'), '--replicates', '1',
                                  '--max-paraphrase', '2']
    return 'x1_transfer', ['--bank', str(x / 'templates'), '--spec',
                           str(x / f'spec_transfer_{X1_RUNG}.csv'), '--replicates', '1',
                           '--framings', 'A,N']


def x1_block(code):
    """The x1 block under the hard session limit; past it, or when the cutoff left scheduled
    runs unstarted, the runner's close-out (CPU only) evaluates finished episodes and gives
    every other scheduled run an infra_failed row."""
    name, extra = x1_args(code)
    res = run_block(code, name, name, extra, hard_at=KERNEL_T0 + float(X1_HARD_S))
    sess = res.get('session') or {}
    # also when the runner stopped starting runs at the cutoff / stop time (rc 0, runs left):
    # x1 sessions are never resumed, so every scheduled run must get its final row now
    if res.get('hard_limit_hit') or sess.get('completed') != sess.get('scheduled'):
        end = KERNEL_T0 + float(X1_SESSION_S) - X1['budget']['seal_reserve_s']
        res['close_out'] = run_block(code, name, name, extra + ['--close-out'],
                                     hard_at=min(time.time() + X1['budget']['close_out_s'], end))
    return res


def x1_select(code):
    """The sealed selector on the complete calibration (pooled, framing-free output)."""
    out_dir = RESULTS_DIR / 'x1_calibration'
    meta = json.loads((out_dir / 'session_summary.json').read_text())
    if meta['completed'] != meta['scheduled'] or meta['needs_adjudication']:
        return {'deferred': True, 'completed': meta['completed'], 'scheduled': meta['scheduled'],
                'needs_adjudication': meta['needs_adjudication']}
    sel = Path('/kaggle/working/x1_selection.json')
    r = subprocess.run([sys.executable, str(code / 'explore' / 'select_x1.py'),
                        str(out_dir / 'runs.csv'), '--analysis',
                        str(code / 'twinguard' / 'twinguard_analysis.py'), '--out', str(sel)],
                       capture_output=True, text=True, cwd=str(code))
    if r.returncode != 0:
        raise RuntimeError(f'selector failed rc={r.returncode}: {redact(r.stderr[-1500:])}')
    s = json.loads(sel.read_text())
    return {'selected': s['selected'], 'rule': s['rule'], 'sha256': sha256(sel)}




if __name__ == '__main__' and MODE == 'eval_check':
    try:
        code = code_dir()
        Path('/tmp/wk').mkdir(parents=True, exist_ok=True)
        if isolation(code)['ok']:
            phase('9_eval_check')(eval_check)(code)
    finally:
        sh('chmod 0755 /kaggle')
        shutil.rmtree('/kaggle/working/code', ignore_errors=True)
        save()
        print('DONE', flush=True)
elif __name__ == '__main__':
    if MODE.startswith('x1_'):
        x1_watchdog()             # before anything else: the whole session is bounded
    if MODE == 'confirmatory':
        R['confirmatory'] = confirmatory_guard()
    gpu_guard()
    if not install_wheels()['ok']:
        raise SystemExit('wheel installation failed: refusing to run')
    procs = []
    verified = False
    try:
        code = code_dir()
        if MODE == 'confirmatory':
            if not phase('6_verify_freeze')(verify_freeze)(code)['ok']:
                raise SystemExit('bundle is not the frozen package: refusing to run')
        if MODE.startswith('x1_'):
            if not phase('6_verify_x1')(x1_verify)(code)['ok']:
                raise SystemExit('bundle is not the sealed D12 package: refusing to run')
        if MODE in FOLLOWUP_MODES:
            if not phase('6_verify_x3')(x3_verify)(code)['ok']:
                raise SystemExit('bundle is not the sealed D15 package: refusing to run')
        if MODE != 'ladder':             # D17 checks each model's files before its own block
            MODEL = model_path()
            R['model_path'] = str(MODEL)
            h = model_hashes()
            if h['ok'] and h.get('all_match'):
                R['verified_revision'] = model_spec()['revision']
            else:
                raise SystemExit(f"served model files do not match HF {model_spec()['revision'][:7]}: "
                                 'refusing to run')
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        restored = phase('8a_restore')(restore_previous)()
        if not restored['ok']:
            raise SystemExit('resume archive check failed: refusing to run')
        if MODE == 'confirmatory':
            if not phase('8c_session_chain')(session_chain)(restored)['ok']:
                raise SystemExit('confirmatory session chain check failed: refusing to run')
        if MODE in FOLLOWUP_MODES:
            if not phase('8c_x3_chain')(x3_chain)(restored)['ok']:
                raise SystemExit('x3 session chain check failed: refusing to run')
        if not isolation(code)['ok']:
            raise SystemExit('isolation checks failed: refusing to run')
        verified = MODE in ('confirmatory',) + FOLLOWUP_MODES   # close-out only under verified isolation

        tp, gpus = (1, '0') if PLATFORM == 'colab' else (4, '0,1,2,3')

        @phase(f'2_server_tp{tp}')
        def up():
            p, secs, ex = start_server(tp, gpus, 8000, f'tp{tp}_8000', ('--uds', str(UDS)))
            procs.append(p)
            R['served_model'] = SERVED[8000]
            return {'load_seconds': secs, 'served': dict(SERVED), 'extra_args': ex}
        if MODE == 'ladder':
            phase('9_ladder')(lambda: ladder_block(code, procs))()
        elif up()['ok'] and server_unreachable()['ok']:
            if MODE == 'pilot':
                main = phase('9_runner_pilot')(lambda: run_block(code, 'pilot', 'pilot', ['--replicates', '1']))()
                if main['ok']:
                    phase('9b_pilot_gates')(lambda: pilot_gates(code))()
                if time.time() < KERNEL_T0 + SESSION_LIMIT_S - STOP_MARGIN_S:
                    phase('9c_seed_diversity')(lambda: diversity_block(code))()
            elif MODE == 'confirmatory':
                phase('9_runner_confirmatory')(lambda: confirmatory_block(code))()
            elif MODE == 'x1_calibration':
                if phase('9_x1_calibration')(lambda: x1_block(code))()['ok']:
                    phase('9b_x1_select')(lambda: x1_select(code))()
            elif MODE == 'x1_transfer':
                phase('9_x1_transfer')(lambda: x1_block(code))()
            elif MODE in FOLLOWUP_MODES:
                phase('9_x3')(lambda: x3_block(code))()
            else:
                if PLATFORM != 'colab' or \
                        phase('4_colab_capacity')(lambda: colab_capacity(f'tp{tp}_8000', procs[0]))()['ok']:
                    phase('9_runner_smoke')(lambda: smoke_block(code))()
    finally:
        stop(procs)
        closed = {'ok': True}
        if verified and deadline_reached():
            # past the deadline: close even if the server or the main block failed (CPU only)
            closed = phase('9d_close_out')(lambda: confirmatory_close_out(code))()
        if verified and x3_deadline_reached():
            closed = {**phase('9d_x3_close_out')(lambda: x3_close_out(code))(), 'ran': True}
        if MODE in FOLLOWUP_MODES:   # before the seal removes the results it reads (Astra/Sol)
            R['x3_status'] = x3_status(closed) if X3 else 'not_started'
        seal = phase('10_seal')(seal_results)()
        sh('chmod 0755 /kaggle')
        shutil.rmtree('/kaggle/working/code', ignore_errors=True)
        for dest in (ladder_dests() if MODE == 'ladder' else [Path(model_spec()['dest'])]):
            shutil.rmtree(dest, ignore_errors=True)
        R['finished'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        R['shard_status'] = shard_status(closed) if MODE == 'confirmatory' else None
        save()
        if not seal['ok'] or not closed['ok']:
            print('SEAL FAILED' if not seal['ok'] else 'CLOSE-OUT FAILED', flush=True)
            sys.exit(1)
        if PLATFORM == 'colab':
            failed = sorted(k for k, v in R['phases'].items() if not v.get('ok'))
            R['colab_failed_phases'] = failed
            save()
            main_phase = {'x3': '9_x3', 'ladder': '9_ladder'}.get(MODE, '9_runner_smoke')
            if failed or main_phase not in R['phases']:
                print(f'COLAB RUN FAILED: {failed}', flush=True)
                sys.exit(1)
        # DONE = the results are sealed; for a shard it also says whether it must be resumed
        print('DONE' + (f" shard_status={R['shard_status']}" if R['shard_status'] else '')
              + (f" x3_status={R['x3_status']}" if R.get('x3_status') else ''), flush=True)
