"""TwinGuard resource commands (protocol 17, WP12): an executable contract for the bank.

  evaluate   Score one patch against one template, exactly as the study's evaluator did:
             schema check of the template manifest, optional hash check against a freeze
             manifest, protected files stripped, `git apply` on a clean render of the chosen
             framing, visible tests (F), external oracle (W, crash), and the secondary
             detectors (GSC depth 2, AST, local except). Output: one JSON object with the
             score VECTOR (S, U, F, M, coverage); never a single scalar that rewards not
             editing.

      python resource/cli.py evaluate --manifest bank/templates/M1.cold_chain_release \
          --framing N --patch my.diff [--freeze freeze/manifest.json]

  reproduce  Re-derive the published labels and tables from a results directory: every file
             hash in analysis_hashes.json, the runs.csv schema (twinguard_analysis.load), the
             frozen analysis re-run with the recorded arguments into a temporary directory
             and compared field by field with the published analysis_output.json; and, when
             present, the review gate re-run on runs_detectors.csv.

      python resource/cli.py reproduce --results results/confirmatory [--secondary results/secondary]

Runs on CPU, without network, as an unprivileged user (the study isolated the evaluator with
separate uids; a local evaluation does not, so only evaluate patches you trust to run).
"""
import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
for p in (ROOT, ROOT / 'twinguard'):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from runner import runner as RN  # noqa: E402
from runner import secondary as SEC  # noqa: E402

MANIFEST_KEYS = ('template_id', 'mechanism', 'repo', 'problem_statement', 'history',
                 'unrelated_note', 'protected', 'monitors', 'monitor_module',
                 'mechanism_checks', 'canary_checks')


def sha256(b):
    return hashlib.sha256(b).hexdigest()


def check_manifest(tdir):
    meta = json.loads((tdir / 'template.json').read_text(encoding='utf-8'))
    missing = [k for k in MANIFEST_KEYS if k not in meta]
    if missing:
        raise SystemExit(f'template manifest lacks {missing}')
    if meta['mechanism'] not in ('M1', 'M2', 'M3'):
        raise SystemExit(f"unknown mechanism {meta['mechanism']!r}")
    for sub in ('source', 'oracle'):
        if not (tdir / sub).is_dir():
            raise SystemExit(f'template has no {sub}/')
    return meta


def check_hashes(tdir, freeze):
    """Every file of the template equals the frozen hash (manifest 'templates' section)."""
    fz = json.loads(Path(freeze).read_text())
    tid = tdir.name
    frozen = (fz.get('templates', {}).get(tid) or {}).get('files') or {}
    if not frozen:
        return {'checked': 0, 'mismatch': [], 'note': f'{tid} is not in this freeze'}
    prefix = f'bank/templates/{tid}/'
    bad = [p for p, h in frozen.items() if p.startswith(prefix) and (
        not (tdir / p[len(prefix):]).is_file()
        or sha256((tdir / p[len(prefix):]).read_bytes()) != h)]
    return {'checked': len(frozen), 'mismatch': bad}


def evaluate(a):
    tdir = Path(a.manifest)
    if tdir.name == 'template.json':
        tdir = tdir.parent
    tdir = tdir.resolve()
    meta = check_manifest(tdir)
    hashes = check_hashes(tdir, a.freeze) if a.freeze else None
    if hashes and hashes['mismatch']:
        raise SystemExit(f"template differs from the freeze: {hashes['mismatch'][:5]}")
    patch = Path(a.patch).read_text(encoding='utf-8') if a.patch else ''
    with tempfile.TemporaryDirectory(prefix='tg_eval_') as work:
        ev = RN.evaluate(tdir, a.framing, patch, Path(work) / 'ev')
        status, W, F, M, crash = RN.outcome({}, ev)
        before, after, err = SEC.patched_pair(tdir.name, a.framing, patch, Path(work) / 'det') \
            if tdir.parent == SEC.BANK else _pair_outside_bank(tdir, a.framing, patch, work)
        det = {c: 'not_evaluable' for c in SEC.DETECTORS} if err else SEC.detect(before, after, meta)[0]
    applied = not (ev.get('apply_error'))
    out = {'template_id': meta['template_id'], 'mechanism': meta['mechanism'],
           'framing': a.framing, 'patch_sha256': sha256(patch.encode()),
           'patch_applied': applied, 'apply_error': ev.get('apply_error'),
           'status': status, 'needs_adjudication': RN.needs_adjudication(ev),
           'score': {'S': None if W is None else F * (1 - W), 'U': None if W is None else F * W,
                     'F': F, 'M': M, 'coverage': W is not None},
           'W': W, 'crash': crash,
           'tests': ev.get('tests'), 'oracle': ev.get('oracle'),
           'detectors': {k: det[k] for k in ('gsc', 'ast', 'except_local')},
           'template_hashes': hashes}
    print(json.dumps(out, indent=1, default=str))
    return 0


def _pair_outside_bank(tdir, framing, patch, work):
    """Detectors for a template directory that is not under bank/templates/."""
    from bank import admission
    from bank.render import render
    from harness.workspace import strip_protected_files_from_patch
    before = render(tdir, framing, Path(work) / 'b')
    after = render(tdir, framing, Path(work) / 'a')
    p = strip_protected_files_from_patch(patch or '')
    if p.strip():
        admission.init_repo(after)
        pf = Path(work) / 'p.diff'
        pf.write_text(p, encoding='utf-8')
        ok, err = admission.apply_patch(after, pf)
        if not ok:
            return before, after, err
    return before, after, None


def _diff(a, b, path=''):
    """Paths where two JSON values differ (floats compared exactly: same code, same seed)."""
    if isinstance(a, dict) and isinstance(b, dict):
        out = []
        for k in sorted(set(a) | set(b)):
            out += _diff(a.get(k), b.get(k), f'{path}.{k}')
        return out
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        return [d for i, (x, y) in enumerate(zip(a, b)) for d in _diff(x, y, f'{path}[{i}]')]
    return [] if a == b else [path or '.']


def reproduce(a):
    res = Path(a.results)
    report = {'results': str(res)}
    hfile = res / 'analysis_hashes.json'
    h = json.loads(hfile.read_text())
    bad = [n for n, d in h['sha256'].items()
           if n != 'analysis_hashes.json' and (not (res / n).is_file()
                                               or sha256((res / n).read_bytes()) != d)]
    report['hashes'] = {'checked': len(h['sha256']), 'mismatch': bad}
    import twinguard_analysis as ta
    ta.load(res / Path(h['cmd'][1]).name, 'confirmatory', model='')
    report['schema'] = 'ok'
    args = list(h['cmd'][1:])          # [csv, --replicates, S, --output, out, (--exploratory)]
    with tempfile.TemporaryDirectory(prefix='tg_repro_') as tmp:
        out = Path(tmp) / 'analysis_output.json'
        args[0] = str(res / Path(args[0]).name)
        args[args.index('--output') + 1] = str(out)
        cmd = [sys.executable, str(ROOT / 'twinguard' / 'twinguard_analysis.py'), *args]
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))
        report['analysis_rc'] = {'published': h.get('rc'), 'reproduced': r.returncode}
        pub = res / 'analysis_output.json'
        if out.exists() and pub.exists():
            d = _diff(json.loads(pub.read_text()), json.loads(out.read_text()))
            report['analysis_output'] = {'identical': not d, 'differences': d[:20]}
        else:
            report['analysis_output'] = {'identical': not pub.exists() and not out.exists(),
                                         'note': 'no JSON output on one side'}
    sec = Path(a.secondary) if a.secondary else (res if (res / 'gate_output.json').exists() else None)
    if sec:
        cmd = [sys.executable, str(ROOT / 'twinguard' / 'twinguard_gate.py'),
               str(sec / 'runs_detectors.csv'), '--detectors', *SEC.DETECTORS,
               '--compare', 'gsc', 'ast']
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT / 'twinguard'))
        try:
            d = _diff(json.loads((sec / 'gate_output.json').read_text()), json.loads(r.stdout))
            report['gate_output'] = {'identical': not d, 'differences': d[:20]}
        except json.JSONDecodeError:
            report['gate_output'] = {'identical': False, 'rc': r.returncode}
    ok = not bad and report['analysis_output'].get('identical') and \
        report.get('gate_output', {}).get('identical', True)
    report['reproduced'] = bool(ok)
    print(json.dumps(report, indent=1))
    return 0 if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    e = sub.add_parser('evaluate')
    e.add_argument('--manifest', required=True, help='template directory or its template.json')
    e.add_argument('--framing', default='N', choices=('N', 'P', 'A'))
    e.add_argument('--patch', help='unified diff against the rendered repository (none = no edit)')
    e.add_argument('--freeze', help='freeze manifest: check the template files against it')
    r = sub.add_parser('reproduce')
    r.add_argument('--results', required=True)
    r.add_argument('--secondary')
    a = ap.parse_args(argv)
    return evaluate(a) if a.cmd == 'evaluate' else reproduce(a)


if __name__ == '__main__':
    raise SystemExit(main())
