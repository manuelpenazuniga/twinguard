"""D17b (ladder2) seal: D17's design and machinery for the two configurations that never started in
D17 session 1 (Gemma 4 E2B and 26B-A4B), whose servers failed on a stale root-only socket left by
the previous server (a kernel bug, fixed by ladder_free_socket), not on the models. Same Colab A100
80 GB path, blocks, analysis and rules as D17 (followup/ladder_seal.py, imported unchanged), with
its own manifest, blocks and global cut. Committed and stamped before any D17b run.

  python followup/ladder2_seal.py        # writes followup/ladder2_manifest.json(.sha256)
"""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from followup import ladder_seal as LS  # noqa: E402  (sealed in D17; imported, never changed)

OUT = ROOT / 'followup' / 'ladder2_manifest.json'
OWN = LS.OWN | {f'followup/ladder2_manifest.json{e}' for e in ('', '.sha256', '.ots')}
BY_MODEL = {b['model']: b for b in LS.BLOCKS}
BLOCKS = [dict(BY_MODEL['e2b'], name='ladder2_e2b_main'), dict(BY_MODEL['26b_a4b'], name='ladder2_26b')]
STOP_AT_UTC = '2026-11-11T21:00:00Z'          # Wed 11 18:00 Chile: no run starts later
STOP_AT_EPOCH = 1794430800
ANALYSIS_PATHS = LS.ANALYSIS_PATHS + ['followup/analyze_ladder2.py', 'followup/ladder_seal.py']


def main(argv=None):
    LS.OUT, LS.OWN, LS.BLOCKS = OUT, OWN, BLOCKS
    LS.STOP_AT_UTC, LS.STOP_AT_EPOCH, LS.ANALYSIS_PATHS = STOP_AT_UTC, STOP_AT_EPOCH, ANALYSIS_PATHS
    LS.main(argv)
    m = json.loads(OUT.read_text())
    m.update(package='TwinGuard D17b: Gemma 4 E2B and 26B-A4B under the D15 request (ladder2), '
                     'the D17 blocks that never started',
             plan='docs/decisions.md D17 and the D17b deviation',
             status='exploratory and descriptive; deviation of D17 (session 1: E2B and 26B-A4B '
                    'startup_failed on a stale server socket, a kernel bug); sealed before any '
                    'D17b run; D17 session 1 and its sealed records are kept unchanged',
             d17_manifest_sha256=(ROOT / 'followup' / 'ladder_manifest.json.sha256').read_text().split()[0],
             analysis={**m['analysis'], 'script': 'followup/analyze_ladder2.py'})
    text = json.dumps(m, indent=1) + '\n'
    OUT.write_text(text)
    digest = hashlib.sha256(text.encode()).hexdigest()
    Path(str(OUT) + '.sha256').write_text(f'{digest}  {OUT.name}\n')
    print(json.dumps({'manifest': str(OUT), 'sha256': digest, 'files': len(m['files'])}))


if __name__ == '__main__':
    main()
