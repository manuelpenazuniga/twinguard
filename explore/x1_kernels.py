"""Build the D12 exploratory kernels from the SEALED D12 commit (never pushes).

Calibration (one kernel, 144 runs):
  python explore/x1_kernels.py calibration --commit D --out-dir DIR
Transfer (two shards, after the calibration kernel's x1_selection.json is in hand):
  python explore/x1_kernels.py transfer --commit D --out-dir DIR --rung L2 \
      --selection-sha256 SHA --calibration-kernel manuelpz/twinguard-x1-cal

Every define the kernel checks is derived here from the sealed explore/x1_manifest.json.
"""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OWNER = 'manuelpz'


def git(*a):
    return subprocess.run(['git', *a], cwd=ROOT, capture_output=True, check=True).stdout


def build(commit, dest, kernel, defines, sources=()):
    Path(dest).mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, str(ROOT / 'notebooks' / 'build_kernel.py'),
           str(ROOT / 'notebooks' / 'pilot_l4'), '--commit', commit, '--out-dir', str(dest),
           '--kernel-id', kernel]
    from explore.x1_seal import EXTRA_PATHS
    for e in EXTRA_PATHS:
        cmd += ['--extra-path', e]
    for d in defines:
        cmd += ['--define', d]
    for s in sources:
        cmd += ['--kernel-source', s]
    subprocess.run(cmd, cwd=ROOT, check=True)
    return {'kernel': kernel, 'dir': str(dest), 'push': f'kaggle kernels push -p {dest}'}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('stage', choices=('calibration', 'transfer'))
    ap.add_argument('--commit', required=True)
    ap.add_argument('--out-dir', required=True)
    ap.add_argument('--rung', choices=('L1', 'L2', 'L3'))
    ap.add_argument('--selection-sha256', default='')
    ap.add_argument('--calibration-kernel', default=f'{OWNER}/twinguard-x1-cal')
    ap.add_argument('--calibration-hours', type=float, default=None,
                    help='measured wall time of the calibration session (its pilot_results.json)')
    a = ap.parse_args(argv)
    full = git('rev-parse', a.commit).decode().strip()
    raw = git('show', f'{full}:explore/x1_manifest.json')
    m = json.loads(raw)
    base = [f'X1_MANIFEST_SHA256={hashlib.sha256(raw).hexdigest()}']
    out = Path(a.out_dir)
    built = []
    if a.stage == 'calibration':
        built.append(build(full, out / 'x1_cal', f'{OWNER}/twinguard-x1-cal',
                           base + ['MODE=x1_calibration',
                                   f"X1_CUTOFF_S={m['budget']['calibration_cutoff_s']}"]))
    else:
        if not a.rung or len(a.selection_sha256) != 64 or a.calibration_hours is None:
            raise SystemExit('transfer needs --rung, --selection-sha256 and --calibration-hours')
        b = m['budget']
        left = (b['cap_hours'] - a.calibration_hours) * 3600 - 2 * b['tail_s_per_session']
        cutoff = int(min(b['transfer_cutoff_s_max'], left / 2))
        if cutoff <= 0:
            raise SystemExit(f'no budget left for the transfer: {left:.0f} s')
        t = m['transfer']
        for i in range(1, t['shards'] + 1):
            shard = f"{i}/{t['shards']}"
            built.append(build(full, out / f'x1_tr_s{i}', f"{OWNER}/twinguard-x1-tr-s{i}of{t['shards']}",
                               base + ['MODE=x1_transfer', f'SHARD={shard}', f'X1_RUNG={a.rung}',
                                       f'X1_SELECTION_SHA256={a.selection_sha256}',
                                       f"X1_STOP_AT_EPOCH={t['stop_at_epoch']}",
                                       f'X1_CUTOFF_S={cutoff}'],
                               [a.calibration_kernel]))
    print(json.dumps(built, indent=1))


if __name__ == '__main__':
    main()
