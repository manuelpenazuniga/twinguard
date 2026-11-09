"""D12 seal: one manifest with the hash of every file the exploratory kernels bundle and run,
read from one commit with `git show` (like freeze/make_freeze.py), plus the D12 parameters.
The manifest is committed and stamped with OpenTimestamps BEFORE the confirmatory is decoded.

  python explore/x1_seal.py [--commit HEAD]     # writes explore/x1_manifest.json(.sha256)
"""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OUT = ROOT / 'explore' / 'x1_manifest.json'
STOP_AT_UTC = '2026-11-11T05:00:00Z'          # Wed 11 02:00 Chile (D12)
STOP_AT_EPOCH = 1794373200
EXTRA_PATHS = ['explore', 'docs/decisions.md']  # bundled in the x1 kernels besides build_kernel.PATHS
BUDGET = {'cap_hours': 6.0, 'calibration_hard_s': 8100, 'transfer_hard_s_max': 6300,
          'start_margin_s': 1200, 'close_out_s': 600, 'session_overhead_s': 900,
          'seal_reserve_s': 300,
          'watchdog': 'the whole session (set-up included) ends at X1_SESSION_S = X1_HARD_S + '
                      'session_overhead_s after kernel start; close-out ends seal_reserve_s before',
          'rule': 'each x1 session stops its runner at X1_HARD_S after start (unfinished runs '
                  'closed out as infra_failed, close-out capped at close_out_s) and starts no run '
                  'after X1_HARD_S - start_margin_s; transfer X1_HARD_S = min(6300, (6 h - '
                  'measured calibration session - 2 x session_overhead_s) / 2), so calibration + '
                  '2 transfer sessions <= 6 h including session_overhead_s each'}


def git(*a):
    return subprocess.run(['git', *a], cwd=ROOT, capture_output=True, check=True).stdout


def bundle_paths():
    src = (ROOT / 'notebooks' / 'build_kernel.py').read_text()
    import ast
    import re
    return ast.literal_eval(re.search(r'PATHS = (\[.*?\])', src, re.S).group(1)) + EXTRA_PATHS


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--commit', default='HEAD')
    a = ap.parse_args(argv)
    commit = git('rev-parse', a.commit).decode().strip()
    if commit != git('rev-parse', 'HEAD').decode().strip() or \
            git('status', '--porcelain', '--untracked-files=no').strip():
        raise SystemExit('seal from a clean checkout of HEAD')
    listed = git('ls-tree', '-r', '--name-only', commit, '--', *bundle_paths()).decode().split('\n')
    files = {}
    own = {'explore/x1_manifest.json', 'explore/x1_manifest.json.sha256', 'explore/x1_manifest.json.ots'}
    for p in sorted(x for x in listed if x and x not in own):
        files[p] = hashlib.sha256(git('show', f'{commit}:{p}')).hexdigest()
    from explore import select_x1 as S
    from explore import analyze_x1 as A
    freeze = json.loads(git('show', f'{commit}:freeze/manifest.json'))
    texts = json.loads(git('show', f'{commit}:explore/bank_x1/texts.json'))
    adm = json.loads(git('show', f'{commit}:explore/bank_x1/admission.json'))
    audit = json.loads(git('show', f'{commit}:explore/bank_x1/audit.json'))
    texts_sha = hashlib.sha256(git('show', f'{commit}:explore/bank_x1/texts.json')).hexdigest()
    build_sha = hashlib.sha256(git('show', f'{commit}:explore/bank_x1/build.json')).hexdigest()
    if not audit.get('pass') or audit.get('texts_sha256') != texts_sha:
        raise SystemExit('the other-family audit must pass on these exact texts')
    if adm['admitted'] != adm['total'] or adm.get('build_sha256') != build_sha \
            or not adm.get('digests_match_build'):
        raise SystemExit('the admission must cover this exact build, all admitted')
    manifest = {
        'package': 'TwinGuard D12 exploratory plan (x1)',
        'commit': commit,
        'commit_utc': git('show', '-s', '--format=%cI', commit).decode().strip(),
        'plan': 'docs/decisions.md D12',
        'freeze_manifest_sha256': hashlib.sha256(git('show', f'{commit}:freeze/manifest.json')).hexdigest(),
        'environment_id': freeze['environment_id'],
        'model': freeze['model'],
        'sampling': freeze['sampling'],
        'texts': {'session_id': texts['session_id'], 'prompt_sha256': texts['prompt_sha256'],
                  'contributing_sha256': texts['contributing_sha256'],
                  'preface_l2': texts['preface_l2'], 'preface_c': texts['preface_c']},
        'admission': {'admitted': adm['admitted'], 'total': adm['total'],
                      'not_admitted': adm['not_admitted'], 'build_sha256': build_sha},
        'audit': {'auditor_model': audit['auditor_model'], 'prompt_sha256': audit['prompt_sha256'],
                  'texts_sha256': texts_sha, 'answer': audit['answer']},
        'calibration': {'spec': 'explore/bank_x1/spec_calibration.csv', 'paraphrases': [1, 2],
                        'replicates': 1, 'framings': ['N', 'P', 'A'], 'runs': 144},
        'selection': {'order': S.ORDER, 'control': S.CONTROL, 'primary_W': S.PRIMARY,
                      'fallback_W': S.FALLBACK, 'target': S.TARGET, 'F_min': S.F_MIN,
                      'F_mechanism_min': S.F_MECH_MIN, 'budget_exhausted_max': S.BUDGET_MAX,
                      'events_primary': S.EVENTS_PRIMARY, 'events_fallback': S.EVENTS_FALLBACK},
        'transfer': {'spec': 'explore/bank_x1/spec_transfer_<rung>.csv', 'framings': ['A', 'N'],
                     'paraphrases': [1, 2, 3, 4], 'replicates': 1, 'runs': 240, 'shards': 2,
                     'stop_at_utc': STOP_AT_UTC, 'stop_at_epoch': STOP_AT_EPOCH,
                     'K_min': A.K_MIN},
        'analysis': {'script': 'explore/analyze_x1.py', 'flags': {
            'floor_or_ceiling': [A.FLOOR, A.CEIL], 'competence_dF': A.F_FLAG,
            'budget_exhausted_rate': A.BUDGET_FLAG}, 'bootstrap': [A.DRAWS, A.SEED]},
        'process_measures': 'explore/process_x1.py',
        'budget': BUDGET,
        'bundle_paths': bundle_paths(),
        'files': files,
    }
    text = json.dumps(manifest, indent=1) + '\n'
    OUT.write_text(text)
    digest = hashlib.sha256(text.encode()).hexdigest()
    Path(str(OUT) + '.sha256').write_text(f'{digest}  {OUT.name}\n')
    print(json.dumps({'manifest': str(OUT), 'sha256': digest, 'files': len(files)}))


if __name__ == '__main__':
    main()
