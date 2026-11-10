"""D16 (e4b) seal: the x3 machinery with Gemma 4 E4B on Kaggle L4x4. One manifest with the hash
of every file the e4b Kaggle kernel bundles (read from one commit with `git show`), the analysis
files, and the D16 parameters. Committed and stamped with OpenTimestamps before the confirmatory is
decoded and before any E4B run.

  python followup/e4b_seal.py         # writes followup/e4b_manifest.json(.sha256)
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from followup.x3_seal import OWN, bundle_paths, git  # noqa: E402

OUT = ROOT / 'followup' / 'e4b_manifest.json'
EXTRA_PATHS = ['followup', 'notebooks/e4b_overlay']    # what build_kernel adds for MODE=e4b
ANALYSIS_PATHS = ['explore/__init__.py', 'explore/process_x1.py', 'explore/bank_x1/texts.json',
                  'twinguard/twinguard_analysis.py', 'twinguard/twinguard_gate.py',
                  'twinguard/twinguard_graph.py', 'runner/runner.py', 'runner/secondary.py',
                  'followup/analyze_x3.py', 'followup/analyze_e4b.py', 'followup/detect_x3.py',
                  'docs/decisions.md']
MODEL = {'hf_id': 'google/gemma-4-E4B-it-qat-w4a16-ct',
         'revision': '6cd26aaa2357fb2bad8c51699a7558a4d1a965bb',
         'kaggle_input': 'google/gemma-4/Other/gemma-4-e4b-it-qat-w4a16-ct/2',
         'overlay': 'notebooks/e4b_overlay (chat_template.jinja, tokenizer_config.json of HF '
                    '6cd26aa; Kaggle v2 ships the older release files)'}
ENVIRONMENT_ID = 'kaggle-L4x4|4 NVIDIA L4|img:37c64f7d|vllm0.19.1|tp4|model:e4b-6cd26aa-overlay'
STOP_AT_UTC = '2026-11-11T18:00:00Z'          # Wed 11 15:00 Chile: no run starts later
STOP_AT_EPOCH = 1794420000
BLOCKS = [{'name': 'e4b_main', 'spec': 'followup/bank_x3/spec_main.csv', 'conditions': ['C'],
           'framings': ['N'], 'runs': 120, 'start_by_epoch': None}]


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
        'package': 'TwinGuard D16 explicit-request follow-up with Gemma 4 E4B (e4b)',
        'mode': 'e4b',
        'commit': commit,
        'commit_utc': git('show', '-s', '--format=%cI', commit).decode().strip(),
        'plan': 'docs/decisions.md D16',
        'status': 'exploratory and descriptive; sealed before the confirmatory is decoded and '
                  'before any E4B run; never pooled with the confirmatory, D12 or x3',
        'environment_id': ENVIRONMENT_ID,
        'model': MODEL,
        'sampling': freeze['sampling'],
        'request_text': texts['preface_c'],
        'admission': {'admitted': adm['admitted'], 'total': adm['total'], 'build_sha256': build_sha},
        'blocks': BLOCKS,
        'order_seed': A.ORDER_SEED, 'paraphrases': [1, 2, 3, 4], 'replicates': 1,
        'stop_at_utc': STOP_AT_UTC, 'stop_at_epoch': STOP_AT_EPOCH,
        'sessions': 'chained (SESSION k resumes k-1 with RESUME_SHA256); unfinished runs are '
                    'closed out only after stop_at',
        'server_hang': 'as D15 (probe /health every 60 s, 30 s timeout, 5 consecutive failures)',
        'runs_csv_model_id': "the sealed runner writes its constant 31B model_id; the E4B rows are "
                             "identified by model_revision 6cd26aa, the runner manifest and the "
                             "environment id",
        'analysis': {'script': 'followup/analyze_e4b.py',
                     'capability_floor': E.FLOOR,
                     'drop_rule': E.DROP_RULE,
                     'reported': 'pooled and per-mechanism W, F, M; tests-pass among W = 1; '
                                 'disclosure, graph tool use and the frozen detectors (as D15); '
                                 "next to x3's C N rows of the same templates (different model "
                                 'AND environment: descriptive only, no test)'},
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
