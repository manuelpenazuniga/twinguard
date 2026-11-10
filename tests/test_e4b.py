"""D16 (e4b): Gemma 4 E4B under the D15 request on Kaggle L4x4, with the x3 machinery: kernel mode,
bundle, model overlay and hashes, seal parameters and the single analysis (synthetic data)."""
import csv
import hashlib
import importlib.util
import io
import json
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))

from followup import analyze_e4b as E, analyze_x3 as AN  # noqa: E402
from runner import runner as R  # noqa: E402
from test_followup_x3 import synth, write, W_effect, results_root as x3_root, M as X3M, SEAL as X3SEAL  # noqa: E402

SCRIPT = ROOT / 'notebooks' / 'pilot_l4' / 'pilot_l4.py'
MODEL = 'google/gemma-4-31b-it-qat-w4a16-ct'


def kernel(monkeypatch, tmp_path, **defs):
    s = importlib.util.spec_from_file_location('tg_kernel_e4b', SCRIPT)
    k = importlib.util.module_from_spec(s)
    s.loader.exec_module(k)
    monkeypatch.setattr(k, 'OUT', tmp_path / 'r.json')
    monkeypatch.setattr(k, 'RESULTS_DIR', tmp_path / 'tgv' / 'results')
    for n, v in defs.items():
        monkeypatch.setattr(k, n, v)
    return k


def git_blob(b):
    return hashlib.sha1(b'blob %d\0' % len(b) + b).hexdigest()


def test_overlay_files_are_hf_6cd26aa():
    from followup import e4b_seal as ES
    k_spec = importlib.util.spec_from_file_location('tg_k0', SCRIPT)
    k = importlib.util.module_from_spec(k_spec)
    k_spec.loader.exec_module(k)
    for name in ('chat_template.jinja', 'tokenizer_config.json'):
        kind, want = k.HF_EXPECTED_E4B[name]
        assert kind == 'git' and git_blob((ROOT / 'notebooks' / 'e4b_overlay' / name).read_bytes()) == want
    assert k.MODEL_SPECS['e4b']['revision'] == ES.MODEL['revision'] == E.REVISION
    assert k.MODEL_SPECS['e4b']['tag'] in ES.ENVIRONMENT_ID
    assert k.MODEL_SPECS['31b']['revision'] == AN.REVISION


def test_e4b_mode_is_kaggle_only_and_uses_its_model(monkeypatch, tmp_path):
    k = kernel(monkeypatch, tmp_path, MODE='e4b', PLATFORM='colab')
    monkeypatch.setattr(k, 'sh', lambda c: 'NVIDIA A100-SXM4-80GB, 81920 MiB, 550\n')
    with pytest.raises(SystemExit, match='never runs on Colab'):
        k.gpu_guard()
    k = kernel(monkeypatch, tmp_path, MODE='e4b', PLATFORM='kaggle')
    monkeypatch.setattr(k, 'sh', lambda c: 'NVIDIA L4, 23034 MiB, 550\n' * 4 if 'query-gpu=name,' in c
                        else '4 NVIDIA L4' if 'uniq' in c else '')
    k.gpu_guard()
    assert k.model_spec()['kaggle'] == 'gemma-4-e4b-it-qat-w4a16-ct/2'
    assert k.environment_id().endswith('|tp4|model:e4b-6cd26aa-overlay')
    assert 'e4b' in k.FOLLOWUP_MODES and str(k.RESULTS_DIR).endswith('results')
    k31 = kernel(monkeypatch, tmp_path, MODE='confirmatory', PLATFORM='kaggle')
    monkeypatch.setattr(k31, 'sh', lambda c: '4 NVIDIA L4')
    assert k31.environment_id() == 'kaggle-L4x4|4 NVIDIA L4|img:37c64f7d|vllm0.19.1|tp4|model:52f3f65-overlay'


def test_e4b_model_path_overlays_hf_files(monkeypatch, tmp_path):
    k = kernel(monkeypatch, tmp_path, MODE='e4b')
    kag = tmp_path / 'input' / 'gemma-4-e4b-it-qat-w4a16-ct' / '2'
    kag.mkdir(parents=True)
    for n in ('model.safetensors', 'chat_template.jinja', 'tokenizer_config.json', 'config.json'):
        (kag / n).write_text('kaggle ' + n)
    dest = tmp_path / 'dest'
    monkeypatch.setitem(k.MODEL_SPECS['e4b'], 'dest', str(dest))
    monkeypatch.setattr(k.glob, 'glob', lambda pat, recursive=False: [str(kag)] if 'e4b' in pat else [])
    monkeypatch.setattr(k, 'code_dir', lambda: ROOT)
    out = k.model_path()
    assert out == dest and (dest / 'model.safetensors').is_symlink()
    assert (dest / 'chat_template.jinja').read_bytes() == \
        (ROOT / 'notebooks' / 'e4b_overlay' / 'chat_template.jinja').read_bytes()


def test_x3_verify_refuses_a_manifest_of_another_mode(monkeypatch, tmp_path):
    code = tmp_path / 'code'
    (code / 'notebooks' / 'pilot_l4').mkdir(parents=True)
    (code / 'notebooks' / 'pilot_l4' / 'pilot_l4.py').write_bytes(b'script')
    blocks = [{'name': 'e4b_main', 'spec': 'followup/bank_x3/spec_main.csv', 'framings': ['N'],
               'start_by_epoch': None}]
    for mode in ('e4b', 'x3'):
        m = {'mode': mode, 'files': {'notebooks/pilot_l4/pilot_l4.py': hashlib.sha256(b'script').hexdigest()},
             'environment_id': 'e', 'stop_at_epoch': 2e9, 'blocks': blocks}
        raw = json.dumps(m).encode()
        (code / 'followup').mkdir(exist_ok=True)
        (code / 'followup' / 'e4b_manifest.json').write_bytes(raw)
        k = kernel(monkeypatch, tmp_path, MODE='e4b', X3_MANIFEST_SHA256=hashlib.sha256(raw).hexdigest(),
                   SCRIPT_SHA256=hashlib.sha256(b'script').hexdigest(), SESSION='1', RESUME_SHA256='', SHARD='')
        if mode == 'e4b':
            assert k.x3_verify(code)['blocks'] == ['e4b_main']
        else:
            with pytest.raises(RuntimeError, match='main block comes first'):
                k.x3_verify(code)


def test_e4b_build_bundles_overlay_and_model_source(tmp_path):
    import base64

    def build(*defs):
        out = tmp_path / ('o' + '_'.join(d.split('=')[1] for d in defs))
        subprocess.run([sys.executable, str(ROOT / 'notebooks' / 'build_kernel.py'),
                        str(ROOT / 'notebooks' / 'pilot_l4'), '--out-dir', str(out),
                        *[x for d in defs for x in ('--define', d)]], check=True, capture_output=True)
        src = (out / 'pilot_l4.py').read_text()
        ns = {}
        i = src.index('CODE_B64')
        exec(src[:src.index('\n', i) + 1], ns)
        names = set(tarfile.open(fileobj=io.BytesIO(base64.b64decode(ns['CODE_B64'])), mode='r:gz').getnames())
        return names, json.loads((out / 'kernel-metadata.json').read_text())
    names, meta = build('MODE=e4b')
    assert 'notebooks/e4b_overlay/chat_template.jinja' in names and 'followup/analyze_x3.py' in names
    assert not any(n.startswith('notebooks/colab') for n in names)
    assert meta['model_sources'] == ['google/gemma-4/Other/gemma-4-e4b-it-qat-w4a16-ct/2']
    names, meta = build('PLATFORM=colab', 'MODE=x3')
    assert not any('e4b_overlay' in n for n in names)
    assert meta['model_sources'] == ['google/gemma-4/Other/gemma-4-31b-it-qat-w4a16-ct/2']


def test_e4b_seal_parameters():
    from followup import e4b_seal as ES, x3_seal as XS
    assert ES.BLOCKS[0]['name'] == 'e4b_main' and ES.BLOCKS[0]['start_by_epoch'] is None
    assert len(AN.scheduled('spec_main.csv', ('N',))) == ES.BLOCKS[0]['runs'] == 120
    assert ES.STOP_AT_EPOCH > XS.STOP_AT_EPOCH
    assert {'followup/e4b_manifest.json', 'followup/x3_manifest.json'} <= ES.OWN
    assert ES.EXTRA_PATHS == ['followup', 'notebooks/e4b_overlay']


def results_root(tmp_path, W_of=W_effect, status_of=None):
    root = tmp_path / 'results'
    sched = AN.scheduled('spec_main.csv', ('N',))
    rows = synth(sched, W_of)
    for r in rows:
        r.update(model_revision=E.REVISION, environment_id='e4')
        if status_of:
            r.update(status_of(r))
    for r in rows:
        r.update(elapsed_seconds='1')
    d = write(rows, root / 'e4b_main')
    (d / 'attempts.jsonl').write_text(''.join(
        json.dumps({'event': 'start', 'run_id': s['run_id'], 'utc': 1.0}) + '\n' for s in sched))
    (d / 'manifest.json').write_text(json.dumps(
        {'environment_id': 'e4', 'model_revision': E.REVISION, 'code_commit': 'c',
         'model_id': MODEL, 'schedule_sha256': R.schedule_digest(sched)}))
    (root / 'x3_sessions.jsonl').write_text(json.dumps(
        {'session': 1, 'manifest_sha256': 'e' * 64, 'code_commit': 'c'}) + '\n')
    return root


M = {'environment_id': 'e4', 'blocks': [{'name': 'e4b_main', 'spec': 'followup/bank_x3/spec_main.csv',
                                         'framings': ['N'], 'start_by_epoch': None}]}


def seals(manifest=None):
    return (X3M, X3SEAL) if manifest == AN.MANIFEST else (M, 'e' * 64)


def test_e4b_end_to_end_with_x3_side_by_side(tmp_path, monkeypatch):
    from followup import detect_x3 as DX
    root = results_root(tmp_path, W_of=lambda s: 1)
    x3 = x3_root(tmp_path / 'x3')
    monkeypatch.setattr(AN, 'verify_seal', seals)
    monkeypatch.setattr(AN, 'CLAIMS', tmp_path / 'claims')
    monkeypatch.setattr(DX, 'run', lambda rows, dirs, out, workers: {'stub': len(rows)})
    E.main(['--results', str(root), '--x3-results', str(x3), '--out', str(tmp_path / 'o')])
    rep = json.loads((tmp_path / 'o' / 'e4b_report.json').read_text())
    assert rep['floor']['met'] and rep['pooled']['W'] == 1.0 and rep['complete_templates'] == 30
    assert rep['vs_x3']['templates'] == 30 and rep['vs_x3']['e4b_W_mean'] == 1.0
    assert rep['x3_comparator']['seal_sha256'] == X3SEAL and len(rep['vs_x3']['per_template']) == 30
    assert rep['vs_x3']['per_template'][0]['e4b_n_evaluable'] == 4
    assert rep['detectors'] == {'stub': 120} and 'C' in rep['row_descriptives']
    assert rep['provenance']['blocks']['e4b_main']['started']


def test_e4b_capability_floor_drops_the_comparison(tmp_path, monkeypatch):
    from followup import detect_x3 as DX
    root = results_root(tmp_path, status_of=lambda r: {'status': 'no_patch', 'M': 0, 'W': 0, 'F': 0})
    monkeypatch.setattr(AN, 'verify_seal', seals)
    monkeypatch.setattr(AN, 'CLAIMS', tmp_path / 'claims')
    monkeypatch.setattr(DX, 'run', lambda rows, dirs, out, workers: {})
    E.main(['--results', str(root), '--x3-results', str(x3_root(tmp_path / 'x3')),
            '--out', str(tmp_path / 'o')])
    rep = json.loads((tmp_path / 'o' / 'e4b_report.json').read_text())
    assert not rep['floor']['met'] and rep['floor']['M_pooled'] == 0.0
    assert rep['vs_x3'] == {'compared': False, 'reason': 'capability floor not met'}


def test_e4b_provenance_uses_its_revision(tmp_path):
    root = results_root(tmp_path)
    AN.provenance(M, 'e' * 64, root, revision=E.REVISION)
    with pytest.raises(SystemExit, match='sealed environment/model'):
        AN.provenance(M, 'e' * 64, root)                 # the 31B revision: refused


def test_unauthenticated_comparator_is_refused_before_the_claim(tmp_path, monkeypatch):
    """Astra/Sol: a wrong x3 directory never yields a comparison, and the claim is not spent."""
    root = results_root(tmp_path, W_of=lambda s: 1)
    bad = tmp_path / 'bad'
    write(synth(AN.scheduled('spec_main.csv', ('N', 'P', 'A')), W_effect), bad / 'x3_main')
    monkeypatch.setattr(AN, 'verify_seal', seals)
    monkeypatch.setattr(AN, 'CLAIMS', tmp_path / 'claims')
    with pytest.raises(SystemExit):
        E.main(['--results', str(root), '--x3-results', str(bad), '--out', str(tmp_path / 'o')])
    assert not (tmp_path / 'claims').exists() or not any((tmp_path / 'claims').iterdir())


def test_e4b_startup_smoke_build(tmp_path):
    """MODEL_KIND=e4b turns the toy-fixture runner smoke into E4B's start-up check (TP=4)."""
    import base64
    out = tmp_path / 'smoke'
    subprocess.run([sys.executable, str(ROOT / 'notebooks' / 'build_kernel.py'),
                    str(ROOT / 'notebooks' / 'pilot_l4'), '--out-dir', str(out),
                    '--kernel-id', 'manuelpz/twinguard-e4b-smoke',
                    '--define', 'MODE=runner_smoke', '--define', 'MODEL_KIND=e4b'],
                   check=True, capture_output=True)
    meta = json.loads((out / 'kernel-metadata.json').read_text())
    assert meta['model_sources'] == ['google/gemma-4/Other/gemma-4-e4b-it-qat-w4a16-ct/2']
    src = (out / 'pilot_l4.py').read_text()
    assert "MODEL_KIND = 'e4b'" in src and "MODE = 'runner_smoke'" in src
