"""D15 (x3) seal: one manifest with the hash of every file the x3 Colab kernel bundles and runs
(read from one commit with `git show`), the analysis files it imports, and the D15 parameters.
Committed and stamped with OpenTimestamps BEFORE the confirmatory is decoded.

  python followup/x3_seal.py          # writes followup/x3_manifest.json(.sha256)
"""
import argparse
import ast
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OUT = ROOT / 'followup' / 'x3_manifest.json'
OWN = {'followup/x3_manifest.json', 'followup/x3_manifest.json.sha256',
       'followup/x3_manifest.json.ots'}
EXTRA_PATHS = ['followup', 'notebooks/colab/kaggle_env']   # bundled besides build_kernel.PATHS
ANALYSIS_PATHS = ['explore/__init__.py', 'explore/build_x1.py', 'explore/admit_x1.py',
                  'explore/process_x1.py', 'explore/bank_x1/texts.json',
                  'twinguard/twinguard_analysis.py', 'runner/runner.py', 'docs/decisions.md']
ENVIRONMENT_ID = 'colab-A100|py3.12|vllm0.19.1|tp1|model:52f3f65-overlay'
STOP_AT_UTC = '2026-11-11T08:00:00Z'          # Wed 11 05:00 Chile: no run starts later
STOP_AT_EPOCH = 1794384000
M3_START_BY_UTC = '2026-11-11T04:00:00Z'      # Wed 11 01:00 Chile: last start of the ablation
M3_START_BY_EPOCH = 1794369600


def git(*a):
    return subprocess.run(['git', *a], cwd=ROOT, capture_output=True, check=True).stdout


def bundle_paths():
    src = (ROOT / 'notebooks' / 'build_kernel.py').read_text()
    return ast.literal_eval(re.search(r'PATHS = (\[.*?\])', src, re.S).group(1)) + EXTRA_PATHS


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.parse_args(argv)
    commit = git('rev-parse', 'HEAD').decode().strip()
    if git('status', '--porcelain', '--untracked-files=no').strip():
        raise SystemExit('seal from a clean checkout of HEAD')
    listed = git('ls-tree', '-r', '--name-only', commit, '--', *bundle_paths()).decode().split('\n')
    h = lambda p: hashlib.sha256(git('show', f'{commit}:{p}')).hexdigest()
    files = {p: h(p) for p in sorted(x for x in listed if x and x not in OWN)}
    analysis = {p: h(p) for p in ANALYSIS_PATHS}
    freeze = json.loads(git('show', f'{commit}:freeze/manifest.json'))
    build_sha = hashlib.sha256(git('show', f'{commit}:followup/bank_x3/build.json')).hexdigest()
    adm = json.loads(git('show', f'{commit}:followup/bank_x3/admission.json'))
    if adm['admitted'] != adm['total'] or adm.get('build_sha256') != build_sha \
            or not adm.get('digests_match_build'):
        raise SystemExit('the admission must cover this exact build, all admitted')
    texts = json.loads(git('show', f'{commit}:explore/bank_x1/texts.json'))
    from followup import analyze_x3 as A
    manifest = {
        'package': 'TwinGuard D15 explicit-request follow-up (x3)',
        'commit': commit,
        'commit_utc': git('show', '-s', '--format=%cI', commit).decode().strip(),
        'plan': 'docs/decisions.md D15',
        'status': 'exploratory; regime chosen post hoc after the pooled D12 calibration; '
                  'sealed before the confirmatory is decoded',
        'freeze_manifest_sha256': hashlib.sha256(git('show', f'{commit}:freeze/manifest.json')).hexdigest(),
        'environment_id': ENVIRONMENT_ID,
        'model': freeze['model'],
        'sampling': freeze['sampling'],
        'request_text': texts['preface_c'],
        'texts_sha256': h('explore/bank_x1/texts.json'),
        'admission': {'admitted': adm['admitted'], 'total': adm['total'], 'build_sha256': build_sha},
        'main': {'spec': 'followup/bank_x3/spec_main.csv', 'condition': 'C',
                 'framings': ['N', 'P', 'A'], 'paraphrases': [1, 2, 3, 4], 'replicates': 1,
                 'runs': 360, 'order_seed': A.ORDER_SEED},
        'm3_ablation': {'spec': 'followup/bank_x3/spec_m3.csv', 'conditions': ['CNH', 'CL1'],
                        'framings': ['N'], 'paraphrases': [1, 2, 3, 4], 'replicates': 1,
                        'runs': 80,
                        'start_rule': 'first run only after every main run has its row and '
                                      'before m3_start_by; then continues until stop_at'},
        'stop_at_utc': STOP_AT_UTC, 'stop_at_epoch': STOP_AT_EPOCH,
        'm3_start_by_utc': M3_START_BY_UTC, 'm3_start_by_epoch': M3_START_BY_EPOCH,
        'sessions': 'chained (SESSION k resumes k-1 with RESUME_SHA256); unfinished runs are '
                    'closed out only after stop_at',
        'analysis': {'script': 'followup/analyze_x3.py', 'K_min_inference': A.K_MIN_INFERENCE,
                     'K_min_estimate': A.K_MIN_ESTIMATE,
                     'frozen': 'twinguard_analysis.py confirmatory_report --exploratory '
                               '--replicates 1 --paraphrases 4 on complete sectors',
                     'process_measures': 'explore/process_x1.py (sealed with D12)'},
        'bundle_paths': bundle_paths(),
        'files': files,
        'analysis_files': analysis,
    }
    text = json.dumps(manifest, indent=1) + '\n'
    OUT.write_text(text)
    digest = hashlib.sha256(text.encode()).hexdigest()
    Path(str(OUT) + '.sha256').write_text(f'{digest}  {OUT.name}\n')
    print(json.dumps({'manifest': str(OUT), 'sha256': digest, 'files': len(files),
                      'analysis_files': len(analysis)}))


if __name__ == '__main__':
    main()
