"""The only sanctioned entry point of the confirmatory analysis (protocol 7.4, 9.5; WP11).

Order: merge, then the 8.6/8.7 detectors and review gate (runner/secondary.py), then the
analysis on runs_detectors.csv (so its GSC decomposition is part of the single run).

Runs the FROZEN code, never the checkout: the merge identifies the sessions' code commit and
checks it holds this freeze manifest; that commit is then extracted (git archive) to a fresh
directory, every frozen file of the extraction is checked against the manifest hashes, and
this same script is re-executed from the extraction. There it merges the shards again
(runner/merge.py, frozen) and runs the frozen twinguard_analysis.py ONCE on the merged CSV
with the flag the truncation report requires: --exploratory whenever any scheduled block is
not complete. The flag cannot be dropped; it can only be added (--exploratory for a
resource-mode run). The output and the verified extraction are hashed.

  python runner/analyze.py --freeze freeze/manifest.json --out results/confirmatory \
      SHARD_DIR [SHARD_DIR ...]
"""
import argparse
import hashlib
import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runner import merge as M  # noqa: E402

FROZEN_ENV = 'TWINGUARD_FROZEN_ROOT'      # set only on the re-execution from the extraction
REPO_ENV = 'TWINGUARD_REPO'               # the git repository the extraction came from
COMMIT_ENV = 'TWINGUARD_FROZEN_COMMIT'    # the commit extracted


def analysis_cmd(csv_path, report, S, output, exploratory=False, root=ROOT):
    cmd = [sys.executable, str(Path(root) / 'twinguard' / 'twinguard_analysis.py'), str(csv_path),
           '--replicates', str(S), '--output', str(output)]
    if report['exploratory_required'] or exploratory:
        cmd.append('--exploratory')
    return cmd


def frozen_files(manifest):
    files = {}
    for group in manifest['files'].values():
        files.update(group)
    for t in manifest['templates'].values():
        files.update(t['files'])
    return files


def extract(commit, repo, dest):
    """git archive of the commit into dest (a fresh directory)."""
    data = subprocess.run(['git', 'archive', '--format=tar', commit], cwd=repo,
                          capture_output=True, check=True).stdout
    with tarfile.open(fileobj=io.BytesIO(data)) as t:
        t.extractall(dest, filter='data')


def verify_extraction(root, manifest, freeze_sha):
    """Every frozen file present with its frozen hash; the manifest is this freeze."""
    root = Path(root)
    if hashlib.sha256((root / 'freeze' / 'manifest.json').read_bytes()).hexdigest() != freeze_sha:
        raise SystemExit('analysis refused: the extracted commit does not hold this freeze')
    bad = [p for p, h in frozen_files(manifest).items()
           if not (root / p).is_file() or hashlib.sha256((root / p).read_bytes()).hexdigest() != h]
    if bad:
        raise SystemExit(f'analysis refused: extracted files differ from the freeze: {bad[:5]}')
    return len(frozen_files(manifest))


MARKER = 'analysis_started.json'
SECONDARY_TIMEOUT_S = 4 * 3600
SENSITIVITY_TIMEOUT_S = 3600       # detectors + gate; then the primary analysis runs anyway
SECONDARY_OUTPUTS = ('runs_detectors.csv', 'detectors.jsonl', 'gate_output.json',
                     'gate_stderr.txt', 'secondary_status.json')


def run_secondary(out, shards, timeout=SECONDARY_TIMEOUT_S):
    """The whole secondary phase (detectors + gate) in its own process group, bounded in
    time; on timeout the group (pool workers included) is killed. Returns None on success,
    else the error text. Success = secondary_status.json written after the gate."""
    import signal
    cmd = [sys.executable, str(ROOT / 'runner' / 'secondary.py'), 'runs', '--runs',
           str(out / 'runs.csv'), '--out', str(out), '--no-hashes', *map(str, shards)]
    p = subprocess.Popen(cmd, cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True, start_new_session=True)
    try:
        _, err = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(p.pid, signal.SIGKILL)
        p.communicate()
        return f'secondary phase exceeded {timeout} s: killed'
    if not (out / 'secondary_status.json').exists():   # a gate exit code alone is recorded
        return f'secondary phase failed (rc {p.returncode}): {err[-400:]}'
    return None


def claim(out, commit):
    """Mutual exclusion for the single run (9.5): atomically create the marker; if it
    exists, another run started (or finished, or was interrupted): refuse."""
    out.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(out / MARKER, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError:
        raise SystemExit('the confirmatory analysis already started once (9.5): refusing')
    with os.fdopen(fd, 'w') as f:
        import time
        f.write(json.dumps({'frozen_commit': commit, 'utc': time.time(), 'pid': os.getpid()}))
        f.flush()
        os.fsync(f.fileno())


def sensitivity_cmd(spec, S, root=ROOT, out=Path('.')):
    """The one prespecified sensitivity invocation; seed and bootstrap are the frozen
    module's defaults (the command passes neither)."""
    return [sys.executable, str(Path(root) / 'twinguard' / 'twinguard_analysis.py'),
            str(Path(out) / 'analysis_sensitivity_input.csv'), '--replicates', str(S),
            '--templates', str(spec['K']), '--output', str(Path(out) / 'analysis_sensitivity.json'),
            '--exploratory']


def run_sensitivity(spec, analysis_input, S, out, timeout=SENSITIVITY_TIMEOUT_S):
    """Prespecified exploratory sensitivity (freeze design.sensitivity): the same frozen
    analysis on the same input without the frozen sectors, always --exploratory, run only
    after a successful primary run whose hashes are already written. Every step is inside
    the guard: a failure (including K or the dropped templates differing from the freeze)
    is recorded and never touches the primary output."""
    import csv
    dst = out / 'analysis_sensitivity_input.csv'
    cmd = None
    try:
        fams = set(spec['exclude_families'])
        with open(analysis_input, newline='', encoding='utf-8') as f, \
                open(dst, 'w', newline='', encoding='utf-8') as g:
            rd = csv.DictReader(f)
            rows = list(rd)
            w = csv.DictWriter(g, fieldnames=rd.fieldnames)
            w.writeheader()
            kept = [row for row in rows if row['family'] not in fams]
            w.writerows(kept)
        dropped = sorted({row['template_id'] for row in rows if row['family'] in fams})
        k = len({row['template_id'] for row in kept})
        if k != spec['K'] or dropped != sorted(spec['templates_dropped']):
            raise ValueError(f'sensitivity input does not match the freeze: K={k} (frozen '
                             f"{spec['K']}), dropped={dropped}")
        cmd = sensitivity_cmd(spec, S, ROOT, out)
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT),
                           timeout=timeout)
        (out / 'analysis_sensitivity.txt').write_text(r.stdout + '\n--- stderr ---\n' + r.stderr)
        return {'cmd': cmd[1:], 'rc': r.returncode, 'templates': k,
                'excluded_families': sorted(fams), 'templates_dropped': dropped}
    except Exception as exc:
        return {'cmd': cmd[1:] if cmd else None, 'error': f'{type(exc).__name__}: {exc}'[:300]}


def seal_sensitivity(out, record, spec, analysis_input, S, primary_rc, seal=None):
    """After the primary seal: run the frozen sensitivity (only if the primary succeeded) and
    seal again with it. The second seal never fails the command; if it fails, the first seal
    (primary, sensitivity 'pending') stands and every reader reports the sensitivity missing."""
    seal = seal or write_hashes
    record['sensitivity'] = run_sensitivity(spec, analysis_input, S, out) \
        if primary_rc == 0 else {'skipped': 'primary analysis failed'}
    try:
        seal(out, record)
        return True
    except Exception as exc:
        (out / 'analysis_hashes.json.tmp').unlink(missing_ok=True)
        print(f'sensitivity seal failed ({type(exc).__name__}: {exc}); the primary seal stands '
              'and the sensitivity is recorded as pending (missing)', file=sys.stderr)
        return False


def write_hashes(out, record):
    digest = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted(out.iterdir()) if p.is_file() and p.name != 'analysis_hashes.json'}
    tmp = out / 'analysis_hashes.json.tmp'
    tmp.write_text(json.dumps({**record, 'sha256': digest}, indent=1))
    os.replace(tmp, out / 'analysis_hashes.json')


def launch_frozen(a, argv):
    """From a checkout: find the commit (merge validates it holds the freeze), extract it,
    verify it, and re-run this script from the extraction."""
    freeze_text = Path(a.freeze).read_bytes()
    manifest = json.loads(freeze_text)
    _, report = M.merge(a.freeze, a.shards)
    commit = report['code_commit']
    dest = Path(tempfile.mkdtemp(prefix=f'twinguard_frozen_{commit[:12]}_')).resolve()
    extract(commit, ROOT, dest)
    n = verify_extraction(dest, manifest, hashlib.sha256(freeze_text).hexdigest())
    env = {**os.environ, FROZEN_ENV: str(dest), REPO_ENV: str(ROOT), COMMIT_ENV: commit}
    absolute = ['--freeze', str(Path(a.freeze).resolve()), '--out', str(Path(a.out).resolve()),
                *(['--exploratory'] if a.exploratory else []),
                *[str(Path(s).resolve()) for s in a.shards]]
    print(json.dumps({'frozen_commit': commit, 'extracted_to': str(dest), 'files_verified': n}))
    r = subprocess.run([sys.executable, str(dest / 'runner' / 'analyze.py'), *absolute],
                       env=env, cwd=str(dest))
    return r.returncode


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--freeze', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--exploratory', action='store_true', help='add the flag (never removes it)')
    ap.add_argument('shards', nargs='+')
    a = ap.parse_args(argv)
    out = Path(a.out).resolve()
    if (out / MARKER).exists() or (out / 'analysis_output.txt').exists():
        raise SystemExit('the confirmatory analysis already ran once (9.5): refusing to rerun')
    frozen_root = os.environ.get(FROZEN_ENV)
    if frozen_root and Path(frozen_root).resolve() != ROOT:
        raise SystemExit('analysis refused: frozen root and this script disagree')
    if not frozen_root:
        rc = launch_frozen(a, argv)
        if rc:
            raise SystemExit(rc)
        return
    # running from the verified extraction of the frozen commit
    repo = os.environ.get(REPO_ENV)
    freeze_text = Path(a.freeze).read_bytes()
    manifest = json.loads(freeze_text)
    verify_extraction(ROOT, manifest, hashlib.sha256(freeze_text).hexdigest())
    rows, report = M.merge(a.freeze, a.shards, repo=repo)
    if report['code_commit'] != os.environ.get(COMMIT_ENV):
        raise SystemExit('analysis refused: extraction is not of the sessions\' commit')
    claim(out, report['code_commit'])           # the single attempt is recorded BEFORE it runs
    M.write(rows, report, out)
    # 8.6/8.7 (D10): detectors on every evaluable run's final patch, then the review gate;
    # the analysis reads runs_detectors.csv so its GSC decomposition (Annex A `gsc`) is computed
    # in the same single run. Detectors never read W. Prespecified failure rule: the secondary
    # analyses never block the primary one. If they fail (any exception, a patch that does
    # not match the evaluated patch), the failure is recorded and the analysis runs on
    # runs.csv without the gsc column; a non-zero gate exit is recorded and nothing else.
    secondary = {'gate_rc': None, 'error': None}
    analysis_input = out / 'runs.csv'
    secondary['error'] = run_secondary(out, a.shards)
    if secondary['error'] is None:
        secondary['gate_rc'] = json.loads((out / 'secondary_status.json').read_text())['gate_rc']
        analysis_input = out / 'runs_detectors.csv'
    else:
        for name in SECONDARY_OUTPUTS:
            (out / name).unlink(missing_ok=True)
    S = manifest['design']['S']
    cmd = analysis_cmd(analysis_input, report, S, out / 'analysis_output.json', a.exploratory)
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))
    (out / 'analysis_output.txt').write_text(r.stdout + '\n--- stderr ---\n' + r.stderr)
    spec = manifest['design'].get('sensitivity')
    record = {'cmd': cmd[1:], 'rc': r.returncode,
              # frozen sensitivity: 'pending' until its own seal; a record still pending means
              # the second seal failed, and every reader reports the sensitivity as missing
              'sensitivity': {'pending': 'runs after the primary seal'} if spec else None,
              'gate_rc': secondary['gate_rc'], 'secondary_error': secondary['error'],
              'frozen_commit': report['code_commit'],
              'code_root': 'git archive of frozen_commit, files verified against the freeze'}
    write_hashes(out, record)                   # the primary is sealed before anything else
    if spec:
        seal_sensitivity(out, record, spec, analysis_input, S, r.returncode)
    print(json.dumps({'rc': r.returncode, 'flag': '--exploratory' in cmd}))
    if r.returncode:
        raise SystemExit(r.returncode)


if __name__ == '__main__':
    main()
