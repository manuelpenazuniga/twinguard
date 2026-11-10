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
# every follow-up manifest (x3: D15, e4b: D16) is excluded from the files it seals, as the kernel does
OWN = {f'followup/{k}_manifest.json{e}' for k in ('x3', 'e4b') for e in ('', '.sha256', '.ots')}
EXTRA_PATHS = ['followup', 'notebooks/colab/kaggle_env']   # bundled besides build_kernel.PATHS
ANALYSIS_PATHS = ['explore/__init__.py', 'explore/build_x1.py', 'explore/admit_x1.py',
                  'explore/process_x1.py', 'explore/bank_x1/texts.json',
                  'twinguard/twinguard_analysis.py', 'twinguard/twinguard_gate.py',
                  'twinguard/twinguard_graph.py', 'runner/runner.py', 'runner/secondary.py',
                  'followup/analyze_x3.py', 'followup/detect_x3.py', 'docs/decisions.md']
ENVIRONMENT_ID = 'colab-A100|py3.12|vllm0.19.1|tp1|model:52f3f65-overlay'
STOP_AT_UTC = '2026-11-11T08:00:00Z'          # Wed 11 05:00 Chile: no run starts later
STOP_AT_EPOCH = 1794384000
EXTRA_START_BY_UTC = '2026-11-11T05:00:00Z'   # Wed 11 02:00 Chile: last first start of an extra block
EXTRA_START_BY_EPOCH = 1794373200
# sealed order: the main block, then the descriptive blocks (each may first start only once every
# earlier block has a row for each of its runs, and before its start_by; time only, never results)
BLOCKS = [
    {'name': 'x3_main', 'spec': 'followup/bank_x3/spec_main.csv', 'conditions': ['C'],
     'framings': ['N', 'P', 'A'], 'runs': 360, 'start_by_epoch': None},
    {'name': 'x3_cw_m3', 'spec': 'followup/bank_x3/spec_cw_m3.csv', 'conditions': ['CW'],
     'framings': ['N'], 'runs': 28, 'start_by_epoch': EXTRA_START_BY_EPOCH},
    {'name': 'x3_m3', 'spec': 'followup/bank_x3/spec_m3.csv', 'conditions': ['CNH', 'CL1'],
     'framings': ['N'], 'runs': 80, 'start_by_epoch': EXTRA_START_BY_EPOCH},
    {'name': 'x3_cw_rest', 'spec': 'followup/bank_x3/spec_cw_rest.csv', 'conditions': ['CW'],
     'framings': ['N'], 'runs': 80, 'start_by_epoch': EXTRA_START_BY_EPOCH},
]


def git(*a):
    return subprocess.run(['git', *a], cwd=ROOT, capture_output=True, check=True).stdout


def bundle_paths(extra=None):
    src = (ROOT / 'notebooks' / 'build_kernel.py').read_text()
    return ast.literal_eval(re.search(r'PATHS = (\[.*?\])', src, re.S).group(1)) + \
        (EXTRA_PATHS if extra is None else extra)


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
    build = json.loads(git('show', f'{commit}:followup/bank_x3/build.json'))
    from followup import analyze_x3 as A
    for b in BLOCKS:
        n = len(A.scheduled(Path(b['spec']).name, tuple(b['framings'])))
        if n != b['runs']:
            raise SystemExit(f"{b['name']}: {n} scheduled runs, sealed {b['runs']}")
    manifest = {
        'package': 'TwinGuard D15 explicit-request follow-up (x3)',
        'mode': 'x3',
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
        'blocks': BLOCKS,
        'block_rule': 'block i > 0 may first start only once every earlier block has a row for '
                      'each of its runs and before its start_by; its first launch passes the '
                      "runner's --stop-at = min(stop_at, start_by); once started it continues "
                      'until stop_at (in later sessions too); a block that never started is not '
                      'closed out; a first start later than start_by + 300 s is excluded as late',
        'order_seed': A.ORDER_SEED, 'paraphrases': [1, 2, 3, 4], 'replicates': 1,
        'cw': {'eligible_base_templates': build['cw_eligible_base_templates'],
               'rule': 'frozen bank/admission/<id>.json criteria.6_oracles: the weak variant is '
                       'detected by the oracle and passes the visible tests',
               'request': 'request_text with weak_variant.diff in place of u_plus.diff'},
        'gpu': 'Colab A100 80 GB (81920 MiB) only, gpu_memory_utilization 0.90; any other card '
               'aborts before the server starts',
        'isolation': 'runner, agents, evaluators and probes in fresh net+IPC namespaces (only a '
                     'down loopback), model reached through a root-owned Unix socket',
        'server_hang': {'probe_s': 60, 'probe_timeout_s': 30, 'consecutive_failures': 5,
                        'action': 'runner and every agent/evaluator killed, block raises, session '
                                  'ends sealed (requires_resume); runs in flight keep their '
                                  'started try'},
        'stop_at_utc': STOP_AT_UTC, 'stop_at_epoch': STOP_AT_EPOCH,
        'extra_start_by_utc': EXTRA_START_BY_UTC, 'extra_start_by_epoch': EXTRA_START_BY_EPOCH,
        'sessions': 'chained (SESSION k resumes k-1 with RESUME_SHA256); unfinished runs are '
                    'closed out only after stop_at',
        'analysis': {'script': 'followup/analyze_x3.py', 'K_min_inference': A.K_MIN_INFERENCE,
                     'K_min_estimate': A.K_MIN_ESTIMATE,
                     'frozen': 'twinguard_analysis.py confirmatory_report --exploratory '
                               '--replicates 1 --paraphrases 4 on complete sectors',
                     'process_measures': 'explore/process_x1.py (sealed with D12)',
                     'outcome_name': 'W = weakening under an explicit request (compliance)',
                     'always_reported': ['K_scheduled', 'K_complete', 'K_paired_A_N',
                                         'flags.truncated', 'not_estimated_reason',
                                         'CONCLUSION_QUALIFIED'],
                     'descriptives': {
                         'detectors': 'followup/detect_x3.py: frozen runner/secondary detectors on '
                                      'the x3 patches; frozen twinguard_gate.py on the main rows',
                         'tests_pass_among_W1': 'F among W = 1 rows (what resolve rate sees)',
                         'disclosure': {'DISCLOSE_RE': A.DISCLOSE_RE.pattern,
                                        'NOT_APPLIED_RE': A.NOT_APPLIED_RE.pattern,
                                        'on': 'final message content'},
                         'graph_tools': list(A.GRAPH_TOOLS),
                         'boundary': list(A.BOUNDARY),
                         'grouping': 'condition and mechanism, never framing'}},
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
