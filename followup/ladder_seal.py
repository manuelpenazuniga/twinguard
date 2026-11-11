"""D17 (ladder) seal: the x3 machinery on x3's Colab A100 80 GB with Gemma 4 26B-A4B, E2B and E4B
(pinned HF revisions), one block per model in a fixed order. One manifest with the hash of every
file the Colab kernel bundles (read from one commit with `git show`), the analysis files and the
D17 parameters. Committed and stamped with OpenTimestamps before any ladder run.

  python followup/ladder_seal.py         # writes followup/ladder_manifest.json(.sha256)
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from followup.x3_seal import bundle_paths, git  # noqa: E402

OUT = ROOT / 'followup' / 'ladder_manifest.json'
OWN = {f'followup/{k}_manifest.json{e}' for k in ('x3', 'e4b', 'ladder') for e in ('', '.sha256', '.ots')}
EXTRA_PATHS = ['followup', 'notebooks/colab/kaggle_env']    # what build_kernel adds for a Colab ladder
ANALYSIS_PATHS = ['explore/__init__.py', 'explore/process_x1.py', 'explore/bank_x1/texts.json',
                  'twinguard/twinguard_analysis.py', 'twinguard/twinguard_gate.py',
                  'twinguard/twinguard_graph.py', 'runner/runner.py', 'runner/secondary.py',
                  'followup/analyze_x3.py', 'followup/analyze_e4b.py', 'followup/analyze_ladder.py',
                  'followup/detect_x3.py', 'docs/decisions.md']
ENV = 'colab-A100|py3.12|vllm0.19.1|tp1|model:'
SPEC = 'followup/bank_x3/spec_main.csv'
# order fixed in D17: the intermediate size first, then the smallest, then E4B again
BLOCKS = [
    {'name': 'ladder_26b_main', 'model': '26b_a4b', 'hf_repo': 'google/gemma-4-26B-A4B-it',
     'revision': '4d7ae4984b7db7de8f8457170b3f1a419ee76d52', 'environment_id': ENV + '26b-a4b-4d7ae49',
     'precision': 'bf16 (no QAT w4a16 release)'},
    {'name': 'ladder_e2b', 'model': 'e2b', 'hf_repo': 'google/gemma-4-E2B-it-qat-w4a16-ct',
     'revision': '971342c08f607aa7779983f6b5289778b5d271a7', 'environment_id': ENV + 'e2b-971342c'},
    {'name': 'ladder_e4b', 'model': 'e4b_hf', 'hf_repo': 'google/gemma-4-E4B-it-qat-w4a16-ct',
     'revision': '6cd26aaa2357fb2bad8c51699a7558a4d1a965bb', 'environment_id': ENV + 'e4b-6cd26aa'},
]
for _b in BLOCKS:
    _b.update(spec=SPEC, conditions=['C'], framings=['N'], runs=120, start_by_epoch=None)
STOP_AT_UTC = '2026-11-11T15:00:00Z'          # Wed 11 12:00 Chile: no run starts later
STOP_AT_EPOCH = 1794409200


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.parse_args(argv)
    commit = git('rev-parse', 'HEAD').decode().strip()
    if git('status', '--porcelain', '--untracked-files=no').strip():
        raise SystemExit('seal from a clean checkout of HEAD')
    paths = bundle_paths(EXTRA_PATHS)
    listed = git('ls-tree', '-r', '--name-only', commit, '--', *paths).decode().split('\n')
    h = lambda p: hashlib.sha256(git('show', f'{commit}:{p}')).hexdigest()
    files = {p: h(p) for p in sorted(x for x in listed if x and x not in OWN)}
    analysis = {p: h(p) for p in ANALYSIS_PATHS}
    freeze = json.loads(git('show', f'{commit}:freeze/manifest.json'))
    adm = json.loads(git('show', f'{commit}:followup/bank_x3/admission.json'))
    build_sha = hashlib.sha256(git('show', f'{commit}:followup/bank_x3/build.json')).hexdigest()
    if adm['admitted'] != adm['total'] or adm.get('build_sha256') != build_sha:
        raise SystemExit('the admission must cover this exact build, all admitted')
    from followup import analyze_e4b as E
    from followup import analyze_x3 as A
    for b in BLOCKS:
        if len(A.scheduled(Path(b['spec']).name, tuple(b['framings']))) != b['runs']:
            raise SystemExit(f"{b['name']}: schedule size differs from the sealed runs")
    texts = json.loads(git('show', f'{commit}:explore/bank_x1/texts.json'))
    manifest = {
        'package': 'TwinGuard D17 Gemma 4 size ladder under the D15 request (ladder)',
        'mode': 'ladder',
        'commit': commit,
        'commit_utc': git('show', '-s', '--format=%cI', commit).decode().strip(),
        'plan': 'docs/decisions.md D17',
        'status': 'exploratory and descriptive; chosen post hoc after the x3 and E4B reports; '
                  'sealed before any ladder run; never pooled with the confirmatory, D12, x3 or D16',
        'environment_id': ENV + '<block model tag>',
        'host': "x3's Colab A100 80 GB, gpu_memory_utilization 0.90, TP 1, vLLM 0.19.1",
        'sampling': freeze['sampling'],
        'request_text': texts['preface_c'],
        'admission': {'admitted': adm['admitted'], 'total': adm['total'], 'build_sha256': build_sha},
        'blocks': BLOCKS,
        'order_rule': 'a block starts only after every earlier block has a row for each run or a '
                      'recorded start-up failure, and before the stop time',
        'startup_failure': 'files failing the hash check, or a server that does not start with the '
                           "default arguments nor with --max-num-seqs 32: the block's "
                           'startup_failed.json is sealed and the next block may start; no other '
                           'version, TP or setting is tried',
        'order_seed': A.ORDER_SEED, 'paraphrases': [1, 2, 3, 4], 'replicates': 1,
        'stop_at_utc': STOP_AT_UTC, 'stop_at_epoch': STOP_AT_EPOCH,
        'sessions': 'chained (SESSION k resumes k-1 with RESUME_SHA256); unfinished runs are '
                    'closed out only after stop_at',
        'server_hang': 'as D15 (probe /health every 60 s, 30 s timeout, 5 consecutive failures)',
        'runs_csv_model_id': "the sealed runner writes its constant 31B model_id; each block's rows "
                             "are identified by the block's model_revision, the runner manifest and "
                             'its environment id',
        'analysis': {'script': 'followup/analyze_ladder.py',
                     'capability_floor': E.FLOOR, 'drop_rule': E.DROP_RULE,
                     'ladder_categories': ['W1', 'W0_tests_pass', 'W0_tests_fail', 'not_evaluable'],
                     'reported': "per model D16's report (floor, pooled/per-mechanism W F M, row "
                                 'descriptives, frozen detectors and gate); the ladder table with '
                                 "the 31B's x3 C N rows; E4B D16 (Kaggle) vs D17 (Colab) per "
                                 'template; descriptive only, no test'},
        'bundle_paths': paths,
        'files': files,
        'analysis_files': analysis,
    }
    text = json.dumps(manifest, indent=1) + '\n'
    OUT.write_text(text)
    digest = hashlib.sha256(text.encode()).hexdigest()
    Path(str(OUT) + '.sha256').write_text(f'{digest}  {OUT.name}\n')
    print(json.dumps({'manifest': str(OUT), 'sha256': digest, 'files': len(files)}))


if __name__ == '__main__':
    main()
