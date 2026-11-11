"""Colab bootstrap for the TwinGuard kernel script (D13 x2 only; the confirmatory and D12 run
on Kaggle). Runs in the Colab notebook process as root, BEFORE the kernel script:

  1. checks the GPU (one A100, 40 or 80 GB);
  2. builds a Python 3.12 virtual environment in /opt (uv; world-executable, as on Kaggle the
     agents run python/pytest from the harness interpreter's bin directory);
  3. downloads, with the author's Kaggle credentials (Colab secrets), the official wheelhouse
     `metric/gemma-4-developer-agent-wheelhouse` and the Kaggle model
     `google/gemma-4/other/gemma-4-31b-it-qat-w4a16-ct/2` into /kaggle/input (the layout the
     kernel script expects), then forgets the credentials;
  4. copies the built kernel script (notebooks/build_kernel.py --define PLATFORM=colab ...)
     from Drive to /kaggle/src/script.py (root only) and, to resume, a previous
     results_sealed.tar.gz into /kaggle/input/prev/ (a resume needs a script REBUILT with
     --define RESUME_SHA256=<sha256 of that archive>; the script refuses any other archive);
  5. runs the script and copies its open outputs (pilot_results.json, the sealed archive,
     vLLM logs) to the Drive run folder every few minutes and at the end.
Drive is mounted under /root (0700), never under /content, so no agent uid can read it.
"""
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

VENV = Path('/opt/tg312')
UV_PY = '/opt/uv-python'
CACHE = '/kaggle/input/kagglehub'
WHEELHOUSE = 'metric/gemma-4-developer-agent-wheelhouse'
MODEL = 'google/gemma-4/other/gemma-4-31b-it-qat-w4a16-ct/2'
# D17 ladder: Hugging Face repos at their pinned revisions (public, not gated), into
# /kaggle/input/hf/<dir> (the kernel's MODEL_SPECS hf_dir; it hash-checks every served file)
LADDER_HF = (('google/gemma-4-26B-A4B-it', '4d7ae4984b7db7de8f8457170b3f1a419ee76d52', 'gemma-4-26b-a4b@4d7ae49'),
             ('google/gemma-4-E2B-it-qat-w4a16-ct', '971342c08f607aa7779983f6b5289778b5d271a7', 'gemma-4-e2b@971342c'),
             ('google/gemma-4-E4B-it-qat-w4a16-ct', '6cd26aaa2357fb2bad8c51699a7558a4d1a965bb', 'gemma-4-e4b@6cd26aa'))
SYNC = ('pilot_results.json', 'results_sealed.tar.gz', 'x2_selection.json', 'pip_freeze.txt')


def sh(cmd, check=True):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if check and r.returncode:
        raise RuntimeError(f'{cmd}\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}')
    return r.stdout.strip()


def gpu():
    g = [l for l in sh('nvidia-smi --query-gpu=name,memory.total --format=csv,noheader').splitlines() if l]
    if len(g) != 1 or 'A100' not in g[0]:
        raise SystemExit(f'need exactly one A100 (Runtime > Change runtime type): {g}')
    return g[0]


def venv():
    if not (VENV / 'bin' / 'python').exists():
        if not shutil.which('uv'):
            sh(f'{sys.executable} -m pip install -q uv')
        env = f'UV_PYTHON_INSTALL_DIR={UV_PY}'
        sh(f'{env} uv python install 3.12')
        sh(f'{env} uv venv --seed --python 3.12 {VENV}')
        sh(f'chmod -R a+rX {UV_PY} {VENV}')
    return {'python': sh(f'{VENV}/bin/python -c "import sys;print(sys.version)"'),
            'uv': sh('uv --version', check=False)}


def writable_input():
    """D17 writes the HF models under /kaggle/input. kagglehub's "Colab cache" mounts Kaggle inputs
    read-only there; a reused runtime may still have that mount: unmount everything under
    /kaggle/input (deepest first) and check that it is writable."""
    root = Path('/kaggle/input')

    def ok():
        try:
            root.mkdir(parents=True, exist_ok=True)
            probe = root / '.tg_write_probe'
            probe.write_text('x')
            probe.unlink()
            return True
        except OSError:
            return False
    if ok():
        return {'unmounted': []}
    mounts = [l.split()[1] for l in Path('/proc/mounts').read_text().splitlines()
              if l.split()[1] == str(root) or l.split()[1].startswith(str(root) + '/')]
    for m in sorted(mounts, key=len, reverse=True):
        sh(f'umount -l {m}', check=False)
    if not ok():
        raise RuntimeError('/kaggle/input is read-only even after unmounting: '
                           'Runtime > Disconnect and delete runtime, then run again')
    return {'unmounted': mounts}


def downloads(user, key, ladder=False):
    """The wheelhouse (Kaggle), then either the 31B Kaggle model or, for D17, the three HF models."""
    if ladder:                                # D17: plain kagglehub downloads, writable /kaggle/input
        os.environ['DISABLE_COLAB_CACHE'] = '1'
        print('input', writable_input(), flush=True)
    os.environ.update(KAGGLE_USERNAME=user, KAGGLE_KEY=key, KAGGLEHUB_CACHE=CACHE)
    try:
        import kagglehub
        whl = kagglehub.dataset_download(WHEELHOUSE)
        mdl = None if ladder else kagglehub.model_download(MODEL)
    finally:
        for k in ('KAGGLE_USERNAME', 'KAGGLE_KEY'):
            os.environ.pop(k, None)
        for p in ('/root/.kaggle', '/root/.config/kaggle'):
            shutil.rmtree(p, ignore_errors=True)
    if ladder and ladder != 'closeout':       # a close-out session after the cut needs no model
        from huggingface_hub import snapshot_download
        mdl = []
        root = Path('/kaggle/input/hf')
        root.mkdir(parents=True, exist_ok=True)
        for repo, rev, d in LADDER_HF:      # Sol: one failed model never stops the others
            dest, err = root / d, None
            for attempt in range(3):
                try:
                    snapshot_download(repo_id=repo, revision=rev, local_dir=str(dest), token=False)
                    shutil.rmtree(dest / '.cache', ignore_errors=True)
                    err = None
                    break
                except Exception as e:
                    err = f'{type(e).__name__}: {e}'[-1500:]
                    time.sleep(30)
            if err:                         # the kernel records this block as startup_failed
                shutil.rmtree(dest, ignore_errors=True)
                (root / (d + '.failed')).write_text(err)
                mdl.append(f'{d}: FAILED {err[:200]}')
            else:
                mdl.append(str(dest))
        sh('chmod -R a+rX /kaggle/input/hf')
    elif ladder:
        mdl = ['closeout: no model downloaded']
    if '/gemma-4-developer-agent-wheelhouse/' not in whl + '/' or not ladder and not mdl.rstrip('/').endswith(
            'gemma-4-31b-it-qat-w4a16-ct/2'):
        raise RuntimeError(f'unexpected download layout: {whl} {mdl}')
    return whl, mdl


def place(script, resume=None):
    for d in ('/kaggle/src', '/kaggle/working', '/kaggle/input'):
        Path(d).mkdir(parents=True, exist_ok=True)
    dst = Path('/kaggle/src/script.py')
    shutil.copyfile(script, dst)
    dst.chmod(0o600)
    if resume:
        prev = Path('/kaggle/input/prev')
        prev.mkdir(exist_ok=True)
        shutil.copyfile(resume, prev / 'results_sealed.tar.gz')
    return sh(f'sha256sum {dst}').split()[0]


def sync(run_dir):
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    w = Path('/kaggle/working')
    names = [n for n in SYNC if (w / n).exists()] + [p.name for p in w.glob('vllm_*.log')]
    names += [f'install/{p.name}' for p in w.glob('install/*.log')]      # pip logs of colab_install
    for name in names:          # copy, then rename: an interruption never destroys the last copy
        dst = run_dir / name.replace('/', '_')
        tmp = dst.with_name(f'.{dst.name}.part')
        shutil.copyfile(w / name, tmp)
        os.replace(tmp, dst)


def run(run_dir, every_s=300):
    log = open('/root/tg_run.log', 'w')
    p = subprocess.Popen([str(VENV / 'bin' / 'python'), '/kaggle/src/script.py'],
                         stdout=log, stderr=subprocess.STDOUT, cwd='/kaggle/working')
    last = 0
    while p.poll() is None:
        time.sleep(20)
        if time.time() - last > every_s:
            sync(run_dir)
            last = time.time()
            tail = Path('/root/tg_run.log').read_text(errors='replace').splitlines()[-1:]
            print(time.strftime('%H:%M:%S'), (tail[0] if tail else '')[:160], flush=True)
    sync(run_dir)
    shutil.copyfile('/root/tg_run.log', Path(run_dir) / 'run.log')
    print('exit', p.returncode, flush=True)
    return p.returncode
