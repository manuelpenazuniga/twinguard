"""Confirmatory mode of the Kaggle kernel and its schedule (WP10), checked offline."""
import csv
import hashlib
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


def confirmatory_kernel():
    k = load_kernel()
    k.MODE = 'confirmatory'
    k.S_REPLICATES, k.FROZEN_COMMIT = '4', 'a' * 40
    k.FREEZE_SHA256, k.SCRIPT_SHA256 = 'f' * 64, 'e' * 64
    k.SHARD, k.SESSION, k.RESUME_SHA256 = '1/2', '1', ''
    return k


def test_guard_fails_closed():
    k = confirmatory_kernel()
    assert k.confirmatory_guard()['shard'] == '1/2'
    for name, bad in (('S_REPLICATES', ''), ('S_REPLICATES', '5'), ('FROZEN_COMMIT', 'b' * 40),
                      ('FREEZE_SHA256', ''), ('SCRIPT_SHA256', ''), ('SHARD', ''),
                      ('SHARD', '3/2'), ('SESSION', ''), ('SESSION', '0'),
                      ('RESUME_SHA256', 'c' * 64)):          # session 1 must not resume
        k = confirmatory_kernel()
        setattr(k, name, bad)
        with pytest.raises(SystemExit):
            k.confirmatory_guard()
    k = confirmatory_kernel()
    k.SESSION = '2'                                         # later sessions must resume
    with pytest.raises(SystemExit):
        k.confirmatory_guard()


def frozen_bundle(tmp_path, k):
    code = tmp_path / 'code'
    files = {'harness/a.py': b'x = 1\n', 'runner/r.py': b'y = 2\n',
             'notebooks/pilot_l4/pilot_l4.py': b'script\n'}
    for rel, data in files.items():
        (code / rel).parent.mkdir(parents=True, exist_ok=True)
        (code / rel).write_bytes(data)
    h = {rel: hashlib.sha256(data).hexdigest() for rel, data in files.items()}
    man = {'design': {'S': 4}, 'confirmatory_deadline_utc': 'x', 'confirmatory_deadline_epoch': 1,
           'files': {'harness': {'harness/a.py': h['harness/a.py']},
                     'runner': {'runner/r.py': h['runner/r.py']},
                     'kernel': {'notebooks/pilot_l4/pilot_l4.py': h['notebooks/pilot_l4/pilot_l4.py'],
                                'docs/not_bundled.md': '0' * 64}},
           'templates': {}}
    (code / 'freeze').mkdir()
    (code / 'freeze' / 'manifest.json').write_text(json.dumps(man))
    k.FREEZE_SHA256 = hashlib.sha256((code / 'freeze' / 'manifest.json').read_bytes()).hexdigest()
    k.SCRIPT_SHA256 = h['notebooks/pilot_l4/pilot_l4.py']
    return code


def test_verify_freeze(tmp_path):
    k = confirmatory_kernel()
    code = frozen_bundle(tmp_path, k)
    assert k.verify_freeze(code)['frozen_files_checked'] == 4
    k2 = confirmatory_kernel()
    frozen_bundle(tmp_path / 'b', k2)
    k2.S_REPLICATES = '3'
    with pytest.raises(RuntimeError):                       # S differs from the freeze
        k2.verify_freeze(tmp_path / 'b' / 'code')
    k3 = confirmatory_kernel()
    c3 = frozen_bundle(tmp_path / 'c', k3)
    (c3 / 'runner' / 'r.py').write_text('y = 3\n')
    with pytest.raises(RuntimeError):                       # modified frozen file
        k3.verify_freeze(c3)
    k4 = confirmatory_kernel()
    c4 = frozen_bundle(tmp_path / 'd', k4)
    (c4 / 'harness' / 'extra.py').write_text('')
    with pytest.raises(RuntimeError):                       # file not in the freeze
        k4.verify_freeze(c4)
    k5 = confirmatory_kernel()
    c5 = frozen_bundle(tmp_path / 'e', k5)
    k5.SCRIPT_SHA256 = '1' * 64
    with pytest.raises(RuntimeError):                       # kernel script is not frozen
        k5.verify_freeze(c5)


def test_session_chain(tmp_path):
    k = confirmatory_kernel()
    k.RESULTS_DIR = tmp_path
    k.FREEZE.update({'confirmatory_deadline_epoch': k.KERNEL_T0 + 99 * 3600})
    e1 = k.session_chain({})
    assert e1['session'] == 1 and not e1['last_session']
    with pytest.raises(RuntimeError):                       # session 1 again: results exist
        k.session_chain({})
    (tmp_path / 'confirmatory' / 'manifest.json').write_text('{}')
    k.SESSION, k.RESUME_SHA256 = '2', 'c' * 64
    e2 = k.session_chain({'parent_seal': {'kind': 'final'}})
    assert e2['parent_sha256'] == 'c' * 64 and e2['parent_seal'] == {'kind': 'final'}
    k.SESSION = '4'                                         # skips session 3
    with pytest.raises(RuntimeError):
        k.session_chain({})
    k.SESSION, k.SHARD = '3', '2/2'                         # other shard's chain
    with pytest.raises(RuntimeError):
        k.session_chain({})


def test_deadline_caps_stop_and_closes():
    k = confirmatory_kernel()
    k.FREEZE.update({'confirmatory_deadline_epoch': k.KERNEL_T0 + 3600})
    assert k.stop_at() == k.KERNEL_T0 + 3600 and k.last_session()
    k.FREEZE.update({'confirmatory_deadline_epoch': k.KERNEL_T0 + 99 * 3600})
    assert k.stop_at() == k.KERNEL_T0 + k.SESSION_LIMIT_S - k.STOP_MARGIN_S
    assert not k.last_session()


def test_runner_cmd_split(tmp_path):
    k = confirmatory_kernel()
    k.FREEZE.update({'confirmatory_deadline_epoch': k.KERNEL_T0 + 99 * 3600})
    k.UDS_DIR = tmp_path
    k.SERVED[8000] = 'm'
    k.R['verified_revision'] = 'r'
    for mode, split in (('confirmatory', 'confirmatory'), ('pilot', 'pilot')):
        k.MODE = mode
        cmd = k.runner_cmd(ROOT, mode, tmp_path / mode, [])
        args = Path(cmd[-1][1:]).read_text().split('\n')
        assert args[args.index('--split') + 1] == split
        assert ('--shard' in args) == (mode == 'confirmatory')


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


def test_build_from_commit(tmp_path):
    out = tmp_path / 'build'
    subprocess.run([sys.executable, str(ROOT / 'notebooks' / 'build_kernel.py'),
                    str(ROOT / 'notebooks' / 'pilot_l4'), '--out-dir', str(out),
                    '--define', 'MODE=confirmatory', '--define', 'S_REPLICATES=4',
                    '--kernel-id', 'u/conf-2', '--kernel-source', 'u/conf-1'],
                   check=True, capture_output=True)
    src = (out / 'pilot_l4.py').read_text()
    assert "MODE = 'confirmatory'" in src and "S_REPLICATES = '4'" in src
    at_head = subprocess.run(['git', 'show', 'HEAD:notebooks/pilot_l4/pilot_l4.py'], cwd=ROOT,
                             capture_output=True, check=True).stdout
    if b'SCRIPT_SHA256 = ' in at_head:
        assert f"SCRIPT_SHA256 = '{hashlib.sha256(at_head).hexdigest()}'" in src
    meta = json.loads((out / 'kernel-metadata.json').read_text())
    assert meta['id'] == 'u/conf-2' and meta['kernel_sources'] == ['u/conf-1']


def test_freeze_s_rule():
    sys.path.insert(0, str(ROOT / 'freeze'))
    import make_freeze as mf
    # T(S) = 30*3*4*S*t_a; with t_a = 60 s: S=4 -> 24 h, S=3 -> 18 h, S=2 -> 12 h
    assert mf.s_rule(60, 40)[0] == 4          # 24 <= 0.6*40
    assert mf.s_rule(60, 30)[0] == 3          # 24 > 18, 18 <= 18
    assert mf.s_rule(60, 20)[0] == 2          # nothing fits: S = 2, declared
    for bad in (0, -1, float('nan'), float('inf')):
        with pytest.raises(SystemExit):
            mf.s_rule(bad, 30)


def test_freeze_k_rule_counts_admission():
    sys.path.insert(0, str(ROOT / 'freeze'))
    import make_freeze as mf
    kr = mf.k_rule('HEAD', None)
    assert kr['K'] == 30 and kr['complete_sectors'] == 10 and not kr['resource_mode']
    assert kr['k_by_mechanism'] == {'M1': 10, 'M2': 10, 'M3': 10}
