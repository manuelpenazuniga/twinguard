"""TwinGuard resource commands (protocol 17, WP12): an executable contract for the bank.

  evaluate   Score one patch against one template, exactly as the study's evaluator did:
             schema check of the template manifest, optional hash check against a freeze
             manifest, protected files stripped, `git apply` on a clean render of the chosen
             framing, visible tests (F), external oracle (W, crash), and the secondary
             detectors (GSC depth 2, AST, local except). Output: one JSON object with the
             score VECTOR (S, U, F, M, coverage); never a single scalar that rewards not
             editing.

      python resource/cli.py evaluate --manifest bank/templates/M1.cold_chain_release \
          --framing N --patch my.diff [--freeze freeze/manifest.json] \
          (--eval-user tgeval0 | --unisolated)

  reproduce  Re-derive the published results from a results directory (runner/analyze.py):
             every file hash in analysis_hashes.json; with --freeze, the code used is the
             frozen code; the runs schema; the analysis and the review gate re-run and
             compared field by field (strict types; both runs must succeed); with --relabel,
             every evaluable label rebuilt from its patch (bound by hash to the evaluated
             patch), visible tests and oracle. Blind adjudications are listed, not re-decided.

      python resource/cli.py reproduce --results results/confirmatory \
          --freeze freeze/manifest.json [--relabel SHARD_DIR ...] [--eval-user U]

Runs on CPU, without network. Evaluating a patch RUNS its code: --eval-user reproduces the
study's isolated evaluator (Linux, root, a dedicated uid); --unisolated runs it as yourself
and is meant only for patches you trust.
"""
import argparse
import hashlib
import json
import shutil
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
    """The template directory IS the frozen template: every frozen file present with its hash
    and no extra file. A template absent from the freeze is refused."""
    fz = json.loads(Path(freeze).read_text())
    tid = tdir.name
    frozen = (fz.get('templates', {}).get(tid) or {}).get('files') or {}
    if not frozen:
        raise SystemExit(f'{tid} is not a template of this freeze')
    prefix = f'bank/templates/{tid}/'
    rel = {p[len(prefix):]: h for p, h in frozen.items() if p.startswith(prefix)}
    present = {p.relative_to(tdir).as_posix() for p in tdir.rglob('*')
               if p.is_file() and '__pycache__' not in p.parts}
    bad = sorted(r for r, h in rel.items()
                 if r not in present or sha256((tdir / r).read_bytes()) != h)
    extra = sorted(present - set(rel))
    return {'checked': len(rel), 'mismatch': bad, 'extra': extra}


def frozen_inputs(freeze, commit=None):
    """Every frozen file (code groups and templates) present in this checkout with its
    frozen hash; and, in a git checkout, the freeze manifest is the one held by the
    published commit."""
    fz_bytes = Path(freeze).read_bytes()
    fz = json.loads(fz_bytes)
    files = {}
    for g in fz['files'].values():
        files.update(g)
    for t in fz.get('templates', {}).values():
        files.update(t['files'])
    bad = [p for p, h in files.items()
           if not (ROOT / p).is_file() or sha256((ROOT / p).read_bytes()) != h]
    binding = None
    if commit:
        r = subprocess.run(['git', 'show', f'{commit}:freeze/manifest.json'], cwd=str(ROOT),
                           capture_output=True)
        binding = r.returncode == 0 and r.stdout == fz_bytes
        if not binding:
            bad.append(f'freeze manifest is not the one held by commit {commit}')
    return {'checked': len(files), 'mismatch': bad, 'freeze_held_by_commit': binding}


def redetect(res, shard_dirs, workers):
    """Detector states recomputed from the patches and compared with runs_detectors.csv."""
    import csv
    from concurrent.futures import ProcessPoolExecutor
    finals = SEC.final_events(shard_dirs)
    rows = list(csv.DictReader(open(res / 'runs_detectors.csv', encoding='utf-8')))
    jobs = [(r['run_id'], r['template_id'], r['framing'], SEC.patch_of(finals, r['run_id']))
            for r in rows if r['status'] in SEC.EVALUABLE]
    with ProcessPoolExecutor(workers) as ex:
        got = {rid: s for rid, s, _ in ex.map(SEC.one_run, jobs)}
    want = {r['run_id']: r for r in rows}
    bad = [rid for rid, s in got.items() if any(s[c] != want[rid][c] for c in SEC.DETECTORS)]
    return {'recomputed': len(got), 'mismatch': bad[:50], 'n_mismatch': len(bad)}


def evaluate(a):
    tdir = Path(a.manifest)
    if tdir.name == 'template.json':
        tdir = tdir.parent
    tdir = tdir.resolve()
    meta = check_manifest(tdir)
    hashes = check_hashes(tdir, a.freeze) if a.freeze else None
    if hashes and (hashes['mismatch'] or hashes['extra']):
        raise SystemExit(f"template differs from the freeze: {hashes}")
    if not a.eval_user and not a.unisolated:
        raise SystemExit('evaluate runs the patched code: pass --eval-user USER (Linux, as root: '
                         'the study\'s isolated evaluator) or --unisolated to run it as yourself')
    patch = Path(a.patch).read_text(encoding='utf-8') if a.patch else ''
    work = traversable_tmp('tg_eval_')
    try:
        ev = RN.evaluate(tdir, a.framing, patch, work / 'ev', a.eval_user)
        status, W, F, M, crash = RN.outcome({}, ev)
        before, after, err = SEC.patched_pair(tdir.name, a.framing, patch, Path(work) / 'det') \
            if tdir.parent == SEC.BANK else _pair_outside_bank(tdir, a.framing, patch, work)
        det = {c: 'not_evaluable' for c in SEC.DETECTORS} if err else SEC.detect(before, after, meta)[0]
    finally:
        shutil.rmtree(work, ignore_errors=True)
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
           'template_hashes': hashes,
           'isolation': f'evaluator uid {a.eval_user}' if a.eval_user else 'none (--unisolated)'}
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


MISSING = object()


def _diff(a, b, path=''):
    """Paths where two JSON values differ. Strict: a missing key differs from null, true
    differs from 1, types must match; floats compare exactly (same code, same seed)."""
    if isinstance(a, dict) and isinstance(b, dict):
        out = []
        for k in sorted(set(a) | set(b)):
            out += _diff(a.get(k, MISSING), b.get(k, MISSING), f'{path}.{k}')
        return out
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return [path or '.']
        return [d for i, (x, y) in enumerate(zip(a, b)) for d in _diff(x, y, f'{path}[{i}]')]
    if type(a) is not type(b) or a != b:
        return [path or '.']
    return []


def traversable_tmp(prefix):
    """A temporary directory the evaluator uid can traverse (runner.evaluate then makes its
    own stage directories private to that uid)."""
    d = Path(tempfile.mkdtemp(prefix=prefix))
    d.chmod(0o711)
    return d


def relabel(res, shard_dirs, workers, eval_users, unisolated):
    """Rebuild every evaluable run's labels from its patch: the evaluated patch (bound by
    hash to the final event), applied to a clean render, visible tests and the external
    oracle, with the run's RECORDED episode summary (budget_exhausted is part of the
    label); compared with runs.csv. Runs decided by blind adjudication are listed, not
    re-decided. With --eval-user U1,U2,...: one exclusive evaluator uid per concurrent
    evaluation (as the study's runner slots); otherwise --unisolated is required."""
    import csv
    import queue
    from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
    if not eval_users and not unisolated:
        raise SystemExit('--relabel runs patched code: pass --eval-user U1,U2,... or --unisolated')
    finals = SEC.final_events(shard_dirs)
    rows = [r for r in csv.DictReader(open(res / 'runs.csv', encoding='utf-8'))
            if r['status'] in SEC.EVALUABLE]
    adjudicated = sorted(r['run_id'] for r in rows if finals[r['run_id']][1].get('needs_adjudication'))
    jobs = [(r['run_id'], r['template_id'], r['framing'], SEC.patch_of(finals, r['run_id']),
             finals[r['run_id']][1].get('summary') or {})
            for r in rows if r['run_id'] not in adjudicated]
    if eval_users:
        users = queue.Queue()
        for u in eval_users:
            users.put(u)

        def slot(job):
            u = users.get()
            try:
                return _relabel_one((*job, u))
            finally:
                RN.purge_user(u)
                users.put(u)
        with ThreadPoolExecutor(len(eval_users)) as ex:
            got = dict(ex.map(slot, jobs))
    else:
        with ProcessPoolExecutor(workers) as ex:
            got = dict(ex.map(_relabel_one, [(*j, None) for j in jobs]))
    want = {r['run_id']: r for r in rows}
    diff = [rid for rid, lab in got.items()
            if [str(x) for x in lab] != [want[rid][k] for k in ('status', 'W', 'F', 'M', 'crash')]]
    return {'relabelled': len(got), 'adjudicated_not_relabelled': len(adjudicated),
            'label_mismatch': diff[:50], 'n_label_mismatch': len(diff)}


def _relabel_one(job):
    run_id, tid, framing, patch, summary, eval_user = job
    work = traversable_tmp('tg_relabel_')
    try:
        ev = RN.evaluate(SEC.BANK / tid, framing, patch, work / 'ev', eval_user)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    lab = RN.outcome(summary, ev)
    return run_id, tuple('' if x is None else x for x in lab)


def reproduce(a):
    res = Path(a.results).resolve()
    report = {'results': str(res)}
    h = json.loads((res / 'analysis_hashes.json').read_text())
    bad = [n for n, d in h['sha256'].items()
           if n != 'analysis_hashes.json' and (not (res / n).is_file()
                                               or sha256((res / n).read_bytes()) != d)]
    report['hashes'] = {'checked': len(h['sha256']), 'mismatch': bad}
    if a.freeze:
        report['code'] = frozen_inputs(a.freeze, h.get('frozen_commit'))
    else:
        report['code'] = {'mismatch': ['no --freeze: the checkout code was not verified']}
    import twinguard_analysis as ta
    csv_name = Path(h['cmd'][1]).name
    ta.load(res / csv_name, 'confirmatory', model='')
    report['schema'] = 'ok'
    args = list(h['cmd'][1:])          # [csv, --replicates, S, --output, out, (--exploratory)]
    pub = res / 'analysis_output.json'
    with tempfile.TemporaryDirectory(prefix='tg_repro_') as tmp:
        out = Path(tmp) / 'analysis_output.json'
        args[0] = str(res / csv_name)
        args[args.index('--output') + 1] = str(out)
        cmd = [sys.executable, str(ROOT / 'twinguard' / 'twinguard_analysis.py'), *args]
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))
        report['analysis_rc'] = {'published': h.get('rc'), 'reproduced': r.returncode}
        if h.get('rc') != 0 or r.returncode != 0 or not out.exists() or not pub.exists():
            report['analysis_output'] = {'identical': False,
                                         'note': 'a run failed or an output is missing'}
        else:
            d = _diff(json.loads(pub.read_text()), json.loads(out.read_text()))
            report['analysis_output'] = {'identical': not d, 'differences': d}
    sens = h.get('sensitivity')
    if sens:
        with tempfile.TemporaryDirectory(prefix='tg_repro_s_') as tmp:
            sargs = list(sens['cmd'][1:])
            sargs[0] = str(res / Path(sargs[0]).name)
            o = Path(tmp) / 's.json'
            sargs[sargs.index('--output') + 1] = str(o)
            r = subprocess.run([sys.executable, str(ROOT / 'twinguard' / 'twinguard_analysis.py'),
                                *sargs], capture_output=True, text=True, cwd=str(ROOT))
            pub = res / 'analysis_sensitivity.json'
            ok = sens.get('rc') == 0 and r.returncode == 0 and o.exists() and pub.exists()
            d = _diff(json.loads(pub.read_text()), json.loads(o.read_text())) if ok else ['.']
            report['sensitivity_output'] = {'identical': ok and not d, 'differences': d}
    if (res / 'runs_detectors.csv').exists():
        cmd = [sys.executable, str(ROOT / 'twinguard' / 'twinguard_gate.py'),
               str(res / 'runs_detectors.csv'), '--detectors', *SEC.DETECTORS,
               '--compare', 'gsc', 'ast']
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT / 'twinguard'))
        try:
            d = _diff(json.loads((res / 'gate_output.json').read_text()), json.loads(r.stdout))
            report['gate_output'] = {'identical': r.returncode == 0 and h.get('gate_rc') == 0
                                     and not d, 'rc': r.returncode,
                                     'published_rc': h.get('gate_rc'), 'differences': d}
        except (json.JSONDecodeError, FileNotFoundError):
            report['gate_output'] = {'identical': False, 'rc': r.returncode}
    if a.relabel:
        users = a.eval_user.split(',') if a.eval_user else None
        report['labels'] = relabel(res, a.relabel, a.workers, users, a.unisolated)
        if (res / 'runs_detectors.csv').exists():
            report['detectors'] = redetect(res, a.relabel, a.workers)
    if (res / 'tables.md').exists():
        with tempfile.TemporaryDirectory(prefix='tg_tables_') as tmp:
            t = subprocess.run([sys.executable, str(HERE / 'tables.py'), '--results', str(res),
                                '--out', str(Path(tmp) / 't.md')], capture_output=True, text=True)
            report['tables'] = {'identical': t.returncode == 0 and
                                (Path(tmp) / 't.md').read_text() == (res / 'tables.md').read_text()}
    ok = (not bad and report['analysis_output']['identical']
          and report.get('gate_output', {}).get('identical', True)
          and not report['code'].get('mismatch')
          and report.get('labels', {}).get('n_label_mismatch', 0) == 0
          and report.get('detectors', {}).get('n_mismatch', 0) == 0
          and report.get('tables', {}).get('identical', True)
          and report.get('sensitivity_output', {}).get('identical', True))
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
    e.add_argument('--eval-user', help='run tests/oracle as this uid (Linux, as root)')
    e.add_argument('--unisolated', action='store_true',
                   help='run the patched code as yourself (only for patches you trust)')
    r = sub.add_parser('reproduce')
    r.add_argument('--results', required=True)
    r.add_argument('--freeze', help='verify the code used against the freeze manifest')
    r.add_argument('--relabel', nargs='+', metavar='SHARD_DIR',
                   help='rebuild every label from its patch, tests and oracle')
    r.add_argument('--workers', type=int, default=4)
    r.add_argument('--eval-user', help='comma-separated evaluator uids, one per concurrent evaluation')
    r.add_argument('--unisolated', action='store_true',
                   help='relabel runs patched code as yourself')
    a = ap.parse_args(argv)
    return evaluate(a) if a.cmd == 'evaluate' else reproduce(a)


if __name__ == '__main__':
    raise SystemExit(main())
