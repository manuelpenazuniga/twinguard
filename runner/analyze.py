"""The only sanctioned entry point of the confirmatory analysis (protocol 7.4, 9.5; WP11).

Merges the shards (runner/merge.py, which validates them against the freeze), then runs the
frozen twinguard_analysis.py ONCE on the merged CSV with the flag the truncation report
requires: --exploratory whenever any scheduled block is not complete. The flag cannot be
dropped; it can only be added (--exploratory for a resource-mode run). The output is hashed.

  python runner/analyze.py --freeze freeze/manifest.json --out results/confirmatory \
      SHARD_DIR [SHARD_DIR ...]
"""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runner import merge as M  # noqa: E402


def analysis_cmd(csv_path, report, S, output, exploratory=False):
    cmd = [sys.executable, str(ROOT / 'twinguard' / 'twinguard_analysis.py'), str(csv_path),
           '--replicates', str(S), '--output', str(output)]
    if report['exploratory_required'] or exploratory:
        cmd.append('--exploratory')
    return cmd


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--freeze', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--exploratory', action='store_true', help='add the flag (never removes it)')
    ap.add_argument('shards', nargs='+')
    a = ap.parse_args(argv)
    out = Path(a.out)
    if (out / 'analysis_output.txt').exists():
        raise SystemExit('the confirmatory analysis already ran once (9.5): refusing to rerun')
    rows, report = M.merge(a.freeze, a.shards)
    M.write(rows, report, out)
    S = json.loads(Path(a.freeze).read_text())['design']['S']
    cmd = analysis_cmd(out / 'runs.csv', report, S, out / 'analysis_output.json', a.exploratory)
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))
    (out / 'analysis_output.txt').write_text(r.stdout + '\n--- stderr ---\n' + r.stderr)
    digest = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted(out.iterdir()) if p.is_file()}
    (out / 'analysis_hashes.json').write_text(json.dumps({'cmd': cmd[1:], 'rc': r.returncode,
                                                         'sha256': digest}, indent=1))
    print(json.dumps({'rc': r.returncode, 'flag': '--exploratory' in cmd}))
    if r.returncode:
        raise SystemExit(r.returncode)


if __name__ == '__main__':
    main()
