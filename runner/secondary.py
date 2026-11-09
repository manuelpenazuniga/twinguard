"""Secondary analyses of protocol 8.6 and 8.7 (WP11), fixed before the confirmatory runs.

  runs       For every evaluable confirmatory run, render its template in its framing, apply
             the run's final patch exactly as the evaluator does (protected files stripped,
             `git apply`), and record, from the frozen twinguard_graph.py v0.3:
               gsc        GSC at depth 2 (the prespecified detector)
               gsc_d1     GSC at depth 1  (fixed sensitivity, never chosen afterwards)
               gsc_d3     GSC at depth 3  (fixed sensitivity)
               ast        trivial AST baseline (fewer monitor calls in a surviving function)
               except_local  local `except` fall-through baseline
             Each value is alert / no_alert / not_evaluable. A patch that does not apply, or a
             detector error, is not_evaluable (with the reason in detectors.jsonl). Detectors
             never read W, F or the framing label beyond rendering the run's own repository.
             Writes runs_detectors.csv (runs.csv + the five columns) and detectors.jsonl,
             then runs the frozen twinguard_gate.py once: natural policy for every detector,
             fixed budgets, and the paired sector-bootstrap difference GSC - AST.
  witnesses  The same detectors on the admission patches of every template (S+, U+,
             alt_safe, weak_variant, canary_break; framing N): published, never used to
             admit (8.6, "Sobre testigos").

  python runner/secondary.py runs --runs results/confirmatory/runs.csv --out results/secondary \
      SHARD_DIR [SHARD_DIR ...]
  python runner/secondary.py witnesses --out results/witnesses
"""
import argparse
import csv
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
for p in (ROOT, ROOT / 'twinguard'):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from bank import admission  # noqa: E402
from bank.render import load, render  # noqa: E402
from harness.workspace import strip_protected_files_from_patch  # noqa: E402
import twinguard_graph as tg  # noqa: E402

BANK = ROOT / 'bank' / 'templates'
EVALUABLE = ('patch', 'no_patch', 'budget_exhausted')   # budget_exhausted: its final diff
GATE_TIMEOUT_S = 3 * 3600
DETECTORS = ('gsc', 'gsc_d1', 'gsc_d3', 'ast', 'except_local')
WITNESS_PATCHES = ('s_plus', 'u_plus', 'alt_safe', 'weak_variant', 'canary_break')


def qualify(pattern):
    """Manifest names are short (`release_pallet`); graph ids are qualified
    (`coldchain.dock.release_pallet`): a plain dotted name matches as a suffix after a dot.
    A pattern that already uses regex syntax is kept as written."""
    if re.fullmatch(r'[A-Za-z_][\w.]*', pattern):
        return r'(?:.+\.)?' + re.escape(pattern)
    return pattern


def code_root(repo, dest):
    """Code roots of the detectors (fixed): every file of the repository except directories
    named `tests` at any depth, `.git` and `__pycache__` (test doubles are not the system's
    protected actions or monitors). Symbolic links are never followed: they are copied as
    links and then removed, so a patch cannot make a detector read outside its repository."""
    shutil.copytree(repo, dest, symlinks=True,
                    ignore=shutil.ignore_patterns('tests', '.git', '__pycache__'))
    links = 0
    for p in sorted(Path(dest).rglob('*'), reverse=True):
        if p.is_symlink():
            p.unlink()
            links += 1
    return Path(dest), links


def detect(before, after, meta):
    """The five detector states for one before/after pair of repositories. Each depth and
    each baseline fails independently (an error is not_evaluable for that column only)."""
    out, why = {}, {}
    scratch = Path(tempfile.mkdtemp(prefix='tg_roots_'))
    try:
        (before, lb), (after, la) = code_root(before, scratch / 'b'), code_root(after, scratch / 'a')
        why['symlinks_removed'] = {'before': lb, 'after': la}
        prot_q = [qualify(p) for p in meta['protected']]
        mon_q = [qualify(p) for p in meta['monitors']]
        try:
            g0, g1 = tg.build_graph(before), tg.build_graph(after)
            graph_error = None
        except Exception as exc:
            graph_error = f'{type(exc).__name__}: {exc}'[:200]
        for col, depth in (('gsc', 2), ('gsc_d1', 1), ('gsc_d3', 3)):
            if graph_error:
                out[col], why[col] = 'not_evaluable', [graph_error]
                continue
            try:
                r = tg.compare(g0, g1, prot_q, mon_q, depth)
                out[col] = r['status']
                why[col] = r['not_evaluable_reasons'] or r['lost_supervision_callers']
                if col == 'gsc':
                    why['matched'] = {'protected': r['before']['protected'],
                                      'monitors': r['before']['monitors']}
            except Exception as exc:
                out[col], why[col] = 'not_evaluable', [f'{type(exc).__name__}: {exc}'[:200]]
        mon, prot = tg._short_names(meta['monitors']), tg._short_names(meta['protected'])
        for col, fn in (('ast', lambda: tg.ast_monitor_call_deletions(before, after, mon)),
                        ('except_local', lambda: tg.except_fallthrough(before, after, mon, prot))):
            try:
                r = fn()
                out[col] = r['status']
                why[col] = r.get('reasons') or r.get('functions_losing_monitor_calls') \
                    or r.get('functions_gaining_fallthrough') or []
            except Exception as exc:
                out[col], why[col] = 'not_evaluable', [f'{type(exc).__name__}: {exc}'[:200]]
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    return out, why


def patched_pair(template_id, framing, patch_text, work, bank=None):
    """(before, after, apply_error): the rendered repository and the same with the patch
    applied as runner.evaluate applies it."""
    tdir = Path(bank or BANK) / template_id
    before = render(tdir, framing, Path(work) / 'before')
    after = render(tdir, framing, Path(work) / 'after')
    patch = strip_protected_files_from_patch(patch_text or '')
    if patch.strip():
        admission.init_repo(after)
        pf = Path(work) / 'final.patch'
        pf.write_text(patch, encoding='utf-8')
        ok, err = admission.apply_patch(after, pf)
        if not ok:
            return before, after, err
        shutil.rmtree(after / '.git', ignore_errors=True)
    return before, after, None


def one_run(job):
    run_id, template_id, framing, patch_text = job
    meta = json.loads((BANK / template_id / 'template.json').read_text())
    with tempfile.TemporaryDirectory(prefix='tg_sec_') as work:
        before, after, err = patched_pair(template_id, framing, patch_text, work)
        if err is not None:
            return run_id, {c: 'not_evaluable' for c in DETECTORS}, {'apply_error': err}
        states, why = detect(before, after, meta)
        return run_id, states, why


EMPTY_SHA = hashlib.sha256(b'').hexdigest()


class PatchMismatch(SystemExit):
    pass


def final_events(shard_dirs):
    """run_id -> (shard_dir, final event), from each shard's own attempts.jsonl."""
    out = {}
    for d in map(Path, shard_dirs):
        for line in (d / 'attempts.jsonl').read_text(encoding='utf-8').splitlines():
            if line.strip():
                e = json.loads(line)
                if e.get('final'):
                    if e['run_id'] in out:
                        raise PatchMismatch(f"{e['run_id']}: final event in more than one shard")
                    out[e['run_id']] = (d, e)
    return out


def patch_of(finals, run_id):
    """The run's final patch, bound to what was evaluated: the file in the run's OWN shard
    whose sha256 equals the final event's patch_sha256. A missing file is accepted only when
    the evaluated patch was empty; anything else refuses (never a silent empty diff)."""
    if run_id not in finals:
        raise PatchMismatch(f'{run_id}: no final event')
    d, e = finals[run_id]
    expected = e.get('patch_sha256')
    f = d / 'patches' / (run_id.replace(':', '__') + '.patch')
    if not f.exists():
        if expected == EMPTY_SHA:
            return ''
        raise PatchMismatch(f'{run_id}: patch file missing but the evaluated patch was not empty')
    text = f.read_text(encoding='utf-8')
    if hashlib.sha256(text.encode()).hexdigest() != expected:
        raise PatchMismatch(f'{run_id}: patch file differs from the evaluated patch')
    return text


def runs_mode(a):
    out = Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    rows = list(csv.DictReader(open(a.runs, encoding='utf-8')))
    finals = final_events(a.shards)
    jobs = [(r['run_id'], r['template_id'], r['framing'], patch_of(finals, r['run_id']))
            for r in rows if r['status'] in EVALUABLE]
    with ProcessPoolExecutor(a.workers) as ex:
        results = {rid: (s, w) for rid, s, w in ex.map(one_run, jobs, chunksize=4)}
    with open(out / 'detectors.jsonl', 'w', encoding='utf-8') as f:
        for rid in sorted(results):
            f.write(json.dumps({'run_id': rid, 'states': results[rid][0],
                                'reasons': results[rid][1]}) + '\n')
    cols = list(rows[0].keys()) + list(DETECTORS)
    with open(out / 'runs_detectors.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            s = results.get(r['run_id'], ({}, {}))[0]
            w.writerow({**r, **{c: s.get(c, '') for c in DETECTORS}})
    cmd = [sys.executable, str(ROOT / 'twinguard' / 'twinguard_gate.py'),
           str(out / 'runs_detectors.csv'), '--detectors', *DETECTORS, '--compare', 'gsc', 'ast']
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT / 'twinguard'),
                       timeout=GATE_TIMEOUT_S)
    (out / 'gate_output.json').write_text(r.stdout)
    (out / 'gate_stderr.txt').write_text(r.stderr)
    (out / 'secondary_status.json').write_text(json.dumps({'gate_rc': r.returncode,
                                                           'runs': len(jobs)}))
    if getattr(a, 'hashes', True):      # analyze.py hashes the whole directory itself
        digest = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in sorted(out.iterdir()) if p.is_file()}
        (out / 'secondary_hashes.json').write_text(json.dumps(
            {'cmd': cmd[1:], 'rc': r.returncode, 'sha256': digest}, indent=1))
    print(json.dumps({'runs': len(jobs), 'gate_rc': r.returncode}))
    return r.returncode


def one_witness(job):
    template_id, kind = job
    t = BANK / template_id
    meta = json.loads((t / 'template.json').read_text())
    pf = t / 'patches' / f'{kind}.diff'
    if not pf.exists():
        return template_id, kind, None, None
    with tempfile.TemporaryDirectory(prefix='tg_wit_') as work:
        before, after, err = patched_pair(template_id, 'N', pf.read_text(encoding='utf-8'), work)
        if err is not None:
            return template_id, kind, {c: 'not_evaluable' for c in DETECTORS}, {'apply_error': err}
        s, w = detect(before, after, meta)
        return template_id, kind, s, w


def witnesses_mode(a):
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    tids = sorted(p.name for p in BANK.iterdir() if (p / 'template.json').exists())
    jobs = [(t, k) for t in tids for k in WITNESS_PATCHES]
    with ProcessPoolExecutor(a.workers) as ex:
        res = list(ex.map(one_witness, jobs))
    table = {}
    with open(out / 'witness_detectors.jsonl', 'w', encoding='utf-8') as f:
        for tid, kind, s, w in res:
            if s is None:
                continue
            f.write(json.dumps({'template_id': tid, 'patch': kind, 'states': s,
                                'reasons': w}) + '\n')
            mech = tid.split('.')[0]
            for c in DETECTORS:
                key = f'{mech}|{kind}|{c}'
                table.setdefault(key, {'alert': 0, 'no_alert': 0, 'not_evaluable': 0})
                table[key][s[c]] += 1
    (out / 'witness_summary.json').write_text(json.dumps(table, indent=1, sort_keys=True))
    print(json.dumps({'templates': len(tids), 'pairs': sum(1 for r in res if r[2] is not None)}))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = ap.add_subparsers(dest='mode', required=True)
    r = sub.add_parser('runs')
    r.add_argument('--runs', required=True)
    r.add_argument('--out', required=True)
    r.add_argument('--workers', type=int, default=4)
    r.add_argument('--no-hashes', dest='hashes', action='store_false')
    r.add_argument('shards', nargs='+')
    w = sub.add_parser('witnesses')
    w.add_argument('--out', required=True)
    w.add_argument('--workers', type=int, default=4)
    a = ap.parse_args(argv)
    raise SystemExit(runs_mode(a) if a.mode == 'runs' else witnesses_mode(a))


if __name__ == '__main__':
    main()
