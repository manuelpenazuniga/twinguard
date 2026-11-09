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
    try:
        from runner import secondary as SEC
        secondary['gate_rc'] = SEC.runs_mode(argparse.Namespace(
            runs=str(out / 'runs.csv'), out=str(out), workers=4, shards=a.shards, hashes=False))
        analysis_input = out / 'runs_detectors.csv'
    except BaseException as exc:          # SystemExit included (PatchMismatch)
        if isinstance(exc, KeyboardInterrupt):
            raise
        secondary['error'] = f'{type(exc).__name__}: {exc}'[:500]
        for name in ('runs_detectors.csv',):
            (out / name).unlink(missing_ok=True)
    S = manifest['design']['S']
    cmd = analysis_cmd(analysis_input, report, S, out / 'analysis_output.json', a.exploratory)
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))
    (out / 'analysis_output.txt').write_text(r.stdout + '\n--- stderr ---\n' + r.stderr)
    digest = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted(out.iterdir()) if p.is_file()}
    (out / 'analysis_hashes.json').write_text(json.dumps(
        {'cmd': cmd[1:], 'rc': r.returncode, 'gate_rc': secondary['gate_rc'],
         'secondary_error': secondary['error'],
         'frozen_commit': report['code_commit'],
         'code_root': 'git archive of frozen_commit, files verified against the freeze',
         'sha256': digest}, indent=1))
    print(json.dumps({'rc': r.returncode, 'flag': '--exploratory' in cmd}))
    if r.returncode:
        raise SystemExit(r.returncode)


if __name__ == '__main__':
    main()
