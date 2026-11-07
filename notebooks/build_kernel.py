"""Bundle the repo code needed on Kaggle into a self-contained script kernel.

Kaggle kernels run offline, so the code travels inside the script as a base64 tar.gz
built from a git commit (default HEAD), never from the working tree. The bundle holds
only tracked files under the given paths.

Usage: python notebooks/build_kernel.py notebooks/smoke_l4 [--commit HEAD]
Writes <kernel_dir>/build/<code_file> and <kernel_dir>/build/kernel-metadata.json.
"""
import argparse
import base64
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATHS = ['harness', 'bank/__init__.py', 'bank/render.py', 'bank/admission.py', 'bank/templates',
         'twinguard/twinguard_graph.py', 'tests/fixtures', 'bank/manipulation_check.py',
         'notebooks/model_overlay', 'runner']
MARKER = '# @@CODE_BUNDLE@@'


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('kernel_dir')
    ap.add_argument('--commit', default='HEAD')
    a = ap.parse_args(argv)
    kdir = Path(a.kernel_dir)
    meta = json.loads((kdir / 'kernel-metadata.json').read_text())
    commit = subprocess.run(['git', 'rev-parse', a.commit], cwd=ROOT, capture_output=True,
                            text=True, check=True).stdout.strip()
    tar = subprocess.run(['git', 'archive', '--format=tar.gz', commit, '--', *PATHS], cwd=ROOT,
                         capture_output=True, check=True).stdout
    src = (kdir / meta['code_file']).read_text()
    if MARKER not in src:
        raise SystemExit(f'{MARKER} not found in {meta["code_file"]}')
    bundle = (f'CODE_COMMIT = {commit!r}\n'
              f'CODE_B64 = {base64.b64encode(tar).decode()!r}\n')
    out = kdir / 'build'
    out.mkdir(exist_ok=True)
    (out / meta['code_file']).write_text(src.replace(MARKER, bundle))
    meta['dataset_sources'] = [d for d in meta.get('dataset_sources', [])
                               if not d.endswith('/twinguard-code')]
    (out / 'kernel-metadata.json').write_text(json.dumps(meta, indent=2) + '\n')
    print(f'{out / meta["code_file"]}: commit {commit[:10]}, bundle {len(tar)} bytes')


if __name__ == '__main__':
    main()
