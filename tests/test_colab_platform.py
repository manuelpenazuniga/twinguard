"""D13: the kernel script's Colab platform (1x A100, TP=1, internet locked per uid). The Kaggle
platform (default) must behave as before; Colab refuses every mode but COLAB_MODES."""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / 'notebooks' / 'pilot_l4' / 'pilot_l4.py'


def load(monkeypatch, tmp_path, **defs):
    s = importlib.util.spec_from_file_location('tg_kernel_colab', SCRIPT)
    k = importlib.util.module_from_spec(s)
    s.loader.exec_module(k)
    monkeypatch.setattr(k, 'OUT', tmp_path / 'r.json')
    for n, v in defs.items():
        monkeypatch.setattr(k, n, v)
    return k


def fake_smi(monkeypatch, k, gpus, calls=None):
    def sh(cmd):
        if calls is not None:
            calls.append(cmd)
        if cmd.startswith('nvidia-smi --query-gpu=name,memory.total'):
            return '\n'.join(gpus)
        return ''
    monkeypatch.setattr(k, 'sh', sh)


L4X4 = ['NVIDIA L4, 23034 MiB'] * 4


def test_default_platform_is_kaggle_and_unchanged(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path)
    assert k.PLATFORM == 'kaggle'
    fake_smi(monkeypatch, k, L4X4)
    assert k.gpu_guard()['ok']
    fake_smi(monkeypatch, k, ['NVIDIA A100-SXM4-80GB, 81920 MiB'])
    with pytest.raises(SystemExit, match='GPU mismatch'):
        k.gpu_guard()
    monkeypatch.setattr(k, 'sh', lambda c: '4 NVIDIA L4')
    assert k.environment_id().startswith('kaggle-L4x4|')


@pytest.mark.parametrize('card', ['NVIDIA A100-SXM4-40GB, 40960 MiB', 'NVIDIA A100-SXM4-80GB, 81920 MiB'])
def test_colab_accepts_one_a100_40_or_80(monkeypatch, tmp_path, card):
    k = load(monkeypatch, tmp_path, PLATFORM='colab', MODE='runner_smoke')
    fake_smi(monkeypatch, k, [card])
    assert k.gpu_guard()['ok'] and k.R['colab_gpu'] == card
    assert k.environment_id() == 'colab-A100|py3.12|vllm0.19.1|tp1|model:52f3f65-overlay'


def test_colab_refuses_other_gpus_and_frozen_modes(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path, PLATFORM='colab', MODE='runner_smoke')
    fake_smi(monkeypatch, k, L4X4)
    with pytest.raises(SystemExit, match='one A100'):
        k.gpu_guard()
    for mode in ('confirmatory', 'pilot', 'x1_calibration', 'x1_transfer', 'eval_check'):
        k2 = load(monkeypatch, tmp_path, PLATFORM='colab', MODE=mode)
        fake_smi(monkeypatch, k2, ['NVIDIA A100-SXM4-80GB, 81920 MiB'])
        with pytest.raises(SystemExit, match='never runs on Colab'):
            k2.gpu_guard()


def test_colab_net_lock_adds_owner_rules_and_fails_closed(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path, PLATFORM='colab')
    calls = []

    def sh(cmd):
        calls.append(cmd)
        return '1' if ' -C ' in cmd else '0'      # no rule yet; -A succeeds
    monkeypatch.setattr(k, 'sh', sh)
    out = k.colab_net_lock()
    users = k.AGENTS + k.EVALS
    assert out['rules'] == 2 * len(users)
    for tool in ('iptables', 'ip6tables'):
        for u in users:
            assert any(c.startswith(f'{tool} -A OUTPUT -m owner --uid-owner {u} ! -o lo -j REJECT')
                       for c in calls)
    monkeypatch.setattr(k, 'sh', lambda c: '1' if ' -C ' in c else '2')
    with pytest.raises(RuntimeError, match='owner rule failed'):
        k.colab_net_lock()


def test_colab_isolation_probes_include_the_network(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path, PLATFORM='colab')
    for name in ('net_tcp_ext', 'net_dns_https', 'net_metadata', 'content_ls', 'proc_env_cat'):
        assert name in k.COLAB_DENIED
    src = SCRIPT.read_text()
    iso = src.split("def isolation(code):")[1].split('\ndef ')[0]
    assert "out['net_lock'] = colab_net_lock()" in iso and 'probes.update(COLAB_DENIED)' in iso
    assert 'if failures:' in iso                     # every probe that succeeds aborts the run


def test_notebook_embeds_the_bootstrap(tmp_path):
    import subprocess
    import sys
    subprocess.run([sys.executable, str(ROOT / 'notebooks' / 'colab' / 'make_notebook.py')], check=True)
    nb = json.loads((ROOT / 'notebooks' / 'colab' / 'twinguard_colab.ipynb').read_text())
    boot = (ROOT / 'notebooks' / 'colab' / 'colab_bootstrap.py').read_text()
    srcs = [c['source'] for c in nb['cells']]
    assert boot in srcs
    assert any("drive.mount('/root/drive')" in s for s in srcs)    # never under /content
    # credentials only from Colab secrets, never written into the notebook
    assert any("downloads(userdata.get('KAGGLE_USERNAME'), userdata.get('KAGGLE_KEY'))" in s
               for s in srcs)
