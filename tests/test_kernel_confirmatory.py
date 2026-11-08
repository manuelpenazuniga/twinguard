"""Confirmatory mode of the Kaggle kernel and its schedule (WP10), checked offline."""
import csv
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from runner.runner import schedule  # noqa: E402


def load_kernel():
    spec = importlib.util.spec_from_file_location('pilot_kernel',
                                                  ROOT / 'notebooks' / 'pilot_l4' / 'pilot_l4.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.CODE_COMMIT = 'a' * 40
    return mod


def test_guard_fails_closed():
    k = load_kernel()
    k.MODE = 'confirmatory'
    with pytest.raises(SystemExit):
        k.confirmatory_guard()                       # S missing
    k.S_REPLICATES = '5'
    k.FROZEN_COMMIT = 'a' * 40
    with pytest.raises(SystemExit):
        k.confirmatory_guard()                       # S outside 9.3
    k.S_REPLICATES = '4'
    k.FROZEN_COMMIT = 'b' * 40
    with pytest.raises(SystemExit):
        k.confirmatory_guard()                       # bundle is not the frozen commit
    k.FROZEN_COMMIT = 'a' * 40
    assert k.confirmatory_guard() == {'S': 4, 'frozen_commit': 'a' * 40, 'close_out': False}


def test_runner_cmd_split(tmp_path):
    k = load_kernel()
    k.UDS_DIR = tmp_path
    k.SERVED[8000] = 'm'
    k.R['verified_revision'] = 'r'
    for mode, split in (('confirmatory', 'confirmatory'), ('pilot', 'pilot')):
        cmd = k.runner_cmd(ROOT, mode, tmp_path / mode, [])
        args = Path(cmd[-1][1:]).read_text().split('\n')
        assert args[args.index('--split') + 1] == split


def test_confirmatory_schedule_blocks():
    runs = schedule(ROOT / 'bank' / 'templates', ROOT / 'bank' / 'spec_matrix.csv',
                    'confirmatory', 4, 20261107)
    assert len(runs) == 30 * 3 * 4 * 4
    fams = [r['family'] for r in runs]
    blocks = [f for i, f in enumerate(fams) if i == 0 or fams[i - 1] != f]
    assert len(blocks) == 10 == len(set(blocks))     # one contiguous block per sector
    for fam in set(fams):
        assert len({r['mechanism'] for r in runs if r['family'] == fam}) == 3
    again = schedule(ROOT / 'bank' / 'templates', ROOT / 'bank' / 'spec_matrix.csv',
                     'confirmatory', 4, 20261107)
    assert [r['run_id'] for r in runs] == [r['run_id'] for r in again]


def test_build_defines_and_kernel_source(tmp_path):
    kdir = tmp_path / 'k'
    shutil.copytree(ROOT / 'notebooks' / 'pilot_l4', kdir,
                    ignore=shutil.ignore_patterns('build', '__pycache__'))
    subprocess.run([sys.executable, str(ROOT / 'notebooks' / 'build_kernel.py'), str(kdir),
                    '--define', 'MODE=confirmatory', '--define', 'S_REPLICATES=4',
                    '--kernel-id', 'u/conf-2', '--kernel-source', 'u/conf-1'],
                   check=True, capture_output=True)
    src = (kdir / 'build' / 'pilot_l4.py').read_text()
    assert "MODE = 'confirmatory'" in src and "S_REPLICATES = '4'" in src
    meta = json.loads((kdir / 'build' / 'kernel-metadata.json').read_text())
    assert meta['id'] == 'u/conf-2' and meta['kernel_sources'] == ['u/conf-1']


def test_freeze_s_rule():
    sys.path.insert(0, str(ROOT / 'freeze'))
    import make_freeze as mf
    # T(S) = 30*3*4*S*t_a; with t_a = 60 s: S=4 -> 24 h, S=3 -> 18 h, S=2 -> 12 h
    assert mf.s_rule(60, 40, 30)[0] == 4          # 24 <= 0.6*40
    assert mf.s_rule(60, 30, 30)[0] == 3          # 24 > 18, 18 <= 18
    assert mf.s_rule(60, 20, 30)[0] == 2          # nothing fits: S = 2, declared
