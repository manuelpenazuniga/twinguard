"""Bundle the repo code needed on Kaggle into a self-contained script kernel.

Kaggle kernels run offline, so the code travels inside the script as a base64 tar.gz
built from a git commit (default HEAD), never from the working tree. The bundle holds
only tracked files under the given paths. The kernel script and its metadata are read from
the same commit; --define only replaces declared top-level constants, and SCRIPT_SHA256
records the hash of the script at the commit (the confirmatory kernel checks it against the
freeze manifest).

Usage: python notebooks/build_kernel.py notebooks/smoke_l4 [--commit HEAD]
Writes <kernel_dir>/build/<code_file> and <kernel_dir>/build/kernel-metadata.json.
"""
import argparse
import base64
import lzma
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COLAB_ENV_PATH = 'notebooks/colab/kaggle_env'
PATHS = ['harness', 'bank/__init__.py', 'bank/render.py', 'bank/admission.py', 'bank/templates',
         'bank/spec_matrix.csv', 'bank/spec_matrix.csv.sha256', 'twinguard/twinguard_graph.py', 'twinguard/twinguard_analysis.py',
         'tests/fixtures', 'bank/manipulation_check.py', 'notebooks/model_overlay', 'runner',
         'notebooks/pilot_l4/pilot_l4.py', 'freeze']
# bank/spec_matrix.csv.sha256 added after the freeze (deviation DEV-1): the frozen kernel's
# verify_freeze matches its BUNDLED prefixes, and 'bank/spec_matrix.csv' also matches the .sha256
# file listed in the manifest, so the bundle must carry it. The bundle content still comes from
# the frozen commit (git archive <commit>).
MARKER = '# @@CODE_BUNDLE@@'
LIMIT = 950_000          # Kaggle: "The kernel source must be less than 1 megabytes in size"


def strip_text(src):
    """Remove docstrings and comments from the kernel script: /kaggle/src may be readable by
    the agent's uid, so the shipped script must not describe the study."""
    import ast
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) \
                and node.body and isinstance(node.body[0], ast.Expr) \
                and isinstance(node.body[0].value, ast.Constant) \
                and isinstance(node.body[0].value.value, str):
            node.body = node.body[1:] or [ast.Pass()]
    return ast.unparse(tree)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('kernel_dir')
    ap.add_argument('--commit', default='HEAD')
    ap.add_argument('--kernel-id', default=None, help='override the metadata id/title')
    ap.add_argument('--out-dir', default=None, help='default <kernel_dir>/build')
    ap.add_argument('--cpu', action='store_true', help='CPU session (no GPU quota)')
    ap.add_argument('--kernel-source', action='append', default=[],
                    help='attach another kernel\'s output (resume: the previous session)')
    ap.add_argument('--extra-path', action='append', default=[],
                    help='D12 only: one more repository path to bundle (e.g. explore)')
    ap.add_argument('--define', action='append', default=[],
                    help="NAME=VALUE: replace the script's top-level `NAME = ...` line")
    a = ap.parse_args(argv)
    kdir = Path(a.kernel_dir).resolve()
    rel = kdir.relative_to(ROOT).as_posix()
    commit = subprocess.run(['git', 'rev-parse', a.commit], cwd=ROOT, capture_output=True,
                            text=True, check=True).stdout.strip()

    def at_commit(name):
        return subprocess.run(['git', 'show', f'{commit}:{rel}/{name}'], cwd=ROOT,
                              capture_output=True, check=True).stdout
    meta = json.loads(at_commit('kernel-metadata.json'))
    if 'PLATFORM=colab' in a.define and COLAB_ENV_PATH not in a.extra_path:
        a.extra_path.append(COLAB_ENV_PATH)        # Colab builds carry the Kaggle environment lock
    if any(f'MODE={m}' in a.define for m in ('x3', 'e4b', 'ladder')) and 'followup' not in a.extra_path:
        a.extra_path.append('followup')            # D15/D16/D17: the derived bank and its manifest
    e4b = 'MODE=e4b' in a.define or 'MODEL_KIND=e4b' in a.define
    if e4b and 'notebooks/e4b_overlay' not in a.extra_path:
        a.extra_path.append('notebooks/e4b_overlay')   # D16: E4B's two HF 6cd26aa files
    tar = subprocess.run(['git', 'archive', '--format=tar.gz', commit, '--', *PATHS, *a.extra_path], cwd=ROOT,
                         capture_output=True, check=True).stdout
    raw = at_commit(meta['code_file'])
    src = raw.decode()
    import hashlib
    if re.search(r'(?m)^SCRIPT_SHA256 = ', src):
        a.define.append(f'SCRIPT_SHA256={hashlib.sha256(raw).hexdigest()}')
    if MARKER not in src:
        raise SystemExit(f'{MARKER} not found in {meta["code_file"]}')
    for d in a.define:
        name, _, value = d.partition('=')
        src, n = re.subn(rf'(?m)^{re.escape(name)} = .*$', f'{name} = {value!r}', src, count=1)
        if n != 1:
            raise SystemExit(f'--define {name}: no top-level assignment found')
    bundle = (f'CODE_COMMIT = {commit!r}\n'
              f'CODE_B64 = {base64.b64encode(tar).decode()!r}\n')
    if len(bundle) + len(src) > LIMIT:
        # Kaggle refuses kernel sources of 1 MB or more (the D12 bundle is ~2.2 MB with gzip).
        # The same tar travels xz-compressed and is re-gzipped at start-up into the identical
        # CODE_B64 the script expects; its integrity is checked file by file by the kernel
        # (x1_verify / verify_freeze), not by the transport.
        raw_tar = subprocess.run(['git', 'archive', '--format=tar', commit, '--', *PATHS,
                                  *a.extra_path], cwd=ROOT, capture_output=True, check=True).stdout
        xz = base64.b64encode(lzma.compress(raw_tar, preset=9 | lzma.PRESET_EXTREME)).decode()
        bundle = ('import base64 as _b64, gzip as _gz, lzma as _xz\n'
                  f'CODE_COMMIT = {commit!r}\n'
                  f'CODE_B64 = _b64.b64encode(_gz.compress(_xz.decompress(_b64.b64decode({xz!r})), '
                  'mtime=0)).decode()\n')
        if len(bundle) + len(src) > LIMIT:
            raise SystemExit(f'kernel source still too large: {len(bundle) + len(src)} bytes')
    out = Path(a.out_dir) if a.out_dir else kdir / 'build'
    out.mkdir(exist_ok=True)
    # bundle first (defined before any use), then the script without docstrings/comments
    (out / meta['code_file']).write_text(bundle + strip_text(src) + '\n')
    if a.kernel_id:
        meta['id'] = a.kernel_id
        meta['title'] = a.kernel_id.split('/')[-1]
    if a.cpu:
        meta['enable_gpu'] = False
        meta.pop('machine_shape', None)
        meta['model_sources'] = []
    if e4b:                                # D16: the E4B model input instead of the 31B
        meta['model_sources'] = ['google/gemma-4/Other/gemma-4-e4b-it-qat-w4a16-ct/2']
    if a.kernel_source:
        meta['kernel_sources'] = list(a.kernel_source)
    meta['dataset_sources'] = [d for d in meta.get('dataset_sources', [])
                               if not d.endswith('/twinguard-code')]
    (out / 'kernel-metadata.json').write_text(json.dumps(meta, indent=2) + '\n')
    print(f'{out / meta["code_file"]}: commit {commit[:10]}, bundle {len(tar)} bytes')


if __name__ == '__main__':
    main()
