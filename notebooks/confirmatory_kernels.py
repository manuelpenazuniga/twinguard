"""Build the confirmatory shard kernels from the FROZEN commit (WP10, D8). Never pushes.

Session 1 of every shard (fresh start):
  python notebooks/confirmatory_kernels.py --commit F --out-dir DIR

Session k > 1 of one shard (resume: attaches the previous session's output and pins the hash
of its results_sealed.tar.gz):
  python notebooks/confirmatory_kernels.py --commit F --out-dir DIR --shard 1/2 --session 2 \
      --resume-sha256 SHA --previous-kernel manuelpz/twinguard-conf-s1-k1

Everything the kernel checks at start is derived here from the frozen manifest held by the
commit (S, shards, manifest hash), so the defines cannot disagree with the freeze. Prints one
`kaggle kernels push -p ...` line per kernel; pushing is a separate, explicit step.
"""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OWNER = 'manuelpz'


def git(*a):
    return subprocess.run(['git', *a], cwd=ROOT, capture_output=True, check=True).stdout


def kernel_id(shard, session):
    i, n = shard.split('/')
    return f'{OWNER}/twinguard-conf-s{i}of{n}-k{session}'


def build(commit, out_dir, shard, session, resume_sha='', previous=None):
    manifest = git('show', f'{commit}:freeze/manifest.json')
    fz = json.loads(manifest)
    if shard not in fz['design']['shards']:
        raise SystemExit(f'shard {shard} is not one of {sorted(fz["design"]["shards"])}')
    if (session == 1) != (not resume_sha):
        raise SystemExit('session 1 starts empty; every later session needs --resume-sha256')
    if session > 1 and not previous:
        raise SystemExit('session > 1 needs --previous-kernel (its output is attached)')
    full = git('rev-parse', commit).decode().strip()
    dest = Path(out_dir) / f'shard{shard.replace("/", "of")}_k{session}'
    dest.mkdir(parents=True, exist_ok=True)
    defines = [f'MODE=confirmatory', f'S_REPLICATES={fz["design"]["S"]}', f'FROZEN_COMMIT={full}',
               f'FREEZE_SHA256={hashlib.sha256(manifest).hexdigest()}', f'SHARD={shard}',
               f'SESSION={session}']
    if resume_sha:
        defines.append(f'RESUME_SHA256={resume_sha}')
    cmd = [sys.executable, str(ROOT / 'notebooks' / 'build_kernel.py'),
           str(ROOT / 'notebooks' / 'pilot_l4'), '--commit', full, '--out-dir', str(dest),
           '--kernel-id', kernel_id(shard, session)]
    for d in defines:
        cmd += ['--define', d]
    if previous:
        cmd += ['--kernel-source', previous]
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
    if r.returncode:
        raise SystemExit(f'build_kernel failed: {r.stderr[-1500:]}')
    meta = json.loads((dest / 'kernel-metadata.json').read_text())
    if meta.get('machine_shape') != 'NvidiaL4' or not meta.get('enable_gpu'):
        raise SystemExit(f'{dest}: not an L4x4 GPU kernel: {meta}')
    script = (dest / meta['code_file']).read_text()
    for d in defines:
        name, val = d.split('=', 1)
        if f"{name} = '{val}'" not in script:
            raise SystemExit(f'{dest}: define {name} missing from the built script')
    return {'kernel': meta['id'], 'dir': str(dest), 'shard': shard, 'session': session,
            'S': fz['design']['S'], 'runs': fz['design']['shards'][shard]['runs'],
            'kernel_sources': meta.get('kernel_sources', []),
            'push': f'kaggle kernels push -p {dest}'}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--commit', required=True, help='the frozen commit (holds freeze/manifest.json)')
    ap.add_argument('--out-dir', required=True)
    ap.add_argument('--shard', help='only this shard (default: every frozen shard, session 1)')
    ap.add_argument('--session', type=int, default=1)
    ap.add_argument('--resume-sha256', default='')
    ap.add_argument('--previous-kernel')
    a = ap.parse_args(argv)
    fz = json.loads(git('show', f'{a.commit}:freeze/manifest.json'))
    shards = [a.shard] if a.shard else sorted(fz['design']['shards'])
    out = [build(a.commit, a.out_dir, s, a.session, a.resume_sha256, a.previous_kernel)
           for s in shards]
    print(json.dumps(out, indent=1))


if __name__ == '__main__':
    main()
