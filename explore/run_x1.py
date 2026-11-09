"""The only sanctioned entry point of the D12 analysis (exploratory; run ONCE).

Before anything is read:
  1. the D12 seal: explore/x1_manifest.json has the hash in explore/x1_manifest.json.sha256,
     an OpenTimestamps proof (explore/x1_manifest.json.ots) exists, and every analysis file
     of this checkout (explore/*, the frozen twinguard_analysis.py, runner/runner.py,
     runner/secondary.py, bank/, harness/) has its sealed hash;
  2. the single run: results/x1/CLAIM is created atomically (O_EXCL); if it exists, refuse;
  3. inputs: the calibration selection has the hash the transfer kernels were built with;
     each transfer shard archive is extracted safely and its rows carry a code commit whose
     explore/x1_manifest.json is the sealed one; confirmatory inputs (N comparison, process
     measures on the confirmatory) are read only after the authorized decoding, i.e. when
     results/confirmatory/analysis_hashes.json exists.

  python explore/run_x1.py --selection x1_selection.json \
      [--transfer SHARD1.tar.gz SHARD2.tar.gz] [--confirmatory-out results/confirmatory \
       --confirmatory-shards DIR ...] --out results/x1
Without --transfer the selection must be 'none' (no transfer was run).
"""
import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
MANIFEST = ROOT / 'explore' / 'x1_manifest.json'
CHECKED = ('explore/', 'twinguard/twinguard_analysis.py', 'runner/runner.py',
           'runner/secondary.py', 'bank/', 'harness/')


def sha(b):
    return hashlib.sha256(b).hexdigest()


def git(*a):
    return subprocess.run(['git', *a], cwd=ROOT, capture_output=True, check=True).stdout


def verify_seal():
    raw = MANIFEST.read_bytes()
    want = (MANIFEST.parent / 'x1_manifest.json.sha256').read_text().split()[0]
    if sha(raw) != want:
        raise SystemExit('x1 manifest hash differs from its .sha256')
    if not (MANIFEST.parent / 'x1_manifest.json.ots').exists():
        raise SystemExit('no OpenTimestamps proof for the x1 manifest')
    m = json.loads(raw)
    bad = [p for p, h in m['files'].items() if p.startswith(CHECKED)
           and (not (ROOT / p).exists() or sha((ROOT / p).read_bytes()) != h)]
    if bad:
        raise SystemExit(f'checkout differs from the sealed D12 files: {bad[:5]}')
    return m, sha(raw)


def claim(out):
    out.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(out / 'CLAIM', os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o444)
    except FileExistsError:
        raise SystemExit(f'{out}/CLAIM exists: the D12 analysis already ran (single run)')
    with os.fdopen(fd, 'w') as fh:
        fh.write(json.dumps({'head': git('rev-parse', 'HEAD').decode().strip()}) + '\n')


def safe_extract(archive, dest):
    with tarfile.open(archive) as t:
        t.extractall(dest, filter='data')


def load_transfer(archives, sealed_sha, work):
    rows, fields, patches = [], None, Path(work) / 'patches'
    patches.mkdir()
    for i, a in enumerate(archives):
        d = Path(work) / f's{i}'
        safe_extract(a, d)
        block = d / 'results' / 'x1_transfer'
        with open(block / 'runs.csv', newline='') as fh:
            rd = csv.DictReader(fh)
            fields = fields or rd.fieldnames
            rows += list(rd)
        for p in (block / 'patches').glob('*.patch'):
            (patches / p.name).write_bytes(p.read_bytes())
    commits = {r['harness_commit'] for r in rows}
    for c in commits:
        if sha(git('show', f'{c}:explore/x1_manifest.json')) != sealed_sha:
            raise SystemExit(f'transfer rows from commit {c[:10]} are not the sealed D12 package')
    merged = Path(work) / 'runs.csv'
    with open(merged, 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    return merged, patches


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--selection', required=True)
    ap.add_argument('--transfer', nargs='*', default=[])
    ap.add_argument('--confirmatory-out', default=None)
    ap.add_argument('--confirmatory-shards', nargs='*', default=[])
    ap.add_argument('--out', required=True)
    a = ap.parse_args(argv)
    m, sealed = verify_seal()
    from explore import analyze_x1 as AX, process_x1 as PX
    sel_raw = Path(a.selection).read_bytes()
    selection = {'sha256': sha(sel_raw), 'content': json.loads(sel_raw)}
    chosen = selection['content']['selected']
    if bool(a.transfer) != (chosen is not None):
        raise SystemExit('transfer archives are required exactly when a rung was selected')
    conf_csv = None
    if a.confirmatory_out:
        co = Path(a.confirmatory_out)
        if not (co / 'analysis_hashes.json').exists():
            raise SystemExit('the confirmatory is not decoded through runner/analyze.py yet')
        conf_csv = co / 'runs.csv'
    out = Path(a.out)
    claim(out)
    res = {'d12_manifest_sha256': sealed, 'calibration': AX.calibration_summary(selection)}
    with tempfile.TemporaryDirectory() as work:
        if chosen:
            runs, patches = load_transfer(a.transfer, sealed, work)
            res['transfer_archives_sha256'] = [sha(Path(x).read_bytes()) for x in a.transfer]
            res['transfer'] = AX.transfer(runs, chosen, selection['sha256'], patches, conf_csv)
            logs = Path(work) / 'logs'
            logs.mkdir()
            for i in range(len(a.transfer)):
                for p in (Path(work) / f's{i}' / 'results' / 'x1_transfer' / 'logs').glob('*.jsonl'):
                    (logs / p.name).write_bytes(p.read_bytes())
            res['process_transfer'] = PX.run(runs, logs, ROOT / 'explore' / 'bank_x1' / 'templates')
        if conf_csv and a.confirmatory_shards:
            clogs = Path(work) / 'clogs'
            clogs.mkdir()
            for d in a.confirmatory_shards:
                for p in Path(d).rglob('logs/*.jsonl'):
                    (clogs / p.name).write_bytes(p.read_bytes())
            res['process_confirmatory'] = PX.run(conf_csv, clogs, ROOT / 'bank' / 'templates')
    text = json.dumps(res, indent=1, allow_nan=False) + '\n'
    (out / 'analysis_x1.json').write_text(text)
    (out / 'analysis_x1.json.sha256').write_text(sha(text.encode()) + '  analysis_x1.json\n')
    print(text)


if __name__ == '__main__':
    main()
