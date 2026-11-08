"""Build the freeze package of protocol 9.4 from one git commit (WP9).

Everything is read from the commit with `git show`, never from the working tree, so anyone
with the repo can rebuild the same manifest and hash:

  python freeze/make_freeze.py --commit HEAD --S 4 --t-a 61.2 --budget-hours 30 \
      --justification "pilot: 81 runs in 1.38 h at concurrency 8 ..." --pilot-sealed-sha256 ...

Writes freeze/manifest.json and freeze/manifest.json.sha256. The SHA-256 is then stamped
with OpenTimestamps (`ots stamp freeze/manifest.json`), which is a separate, explicit step.
The manifest holds hashes and configuration only: no results and no competition data.
"""
import argparse
import csv
import hashlib
import io
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ORDER_SEED = 20261107            # runner default (--order-seed), published here
SAMPLING = {'temperature': 1.0, 'top_p': 0.95, 'top_k': 64}
PARAPHRASES = 4
FRAMINGS = ('N', 'P', 'A')

# groups of files whose individual SHA-256 goes into the manifest
GROUPS = {
    'protocol': ['docs/TwinGuard_v3.6_propuesta.md', 'docs/decisions.md', 'docs/harness.md',
                 'docs/environment.md'],
    'analysis': ['twinguard/twinguard_analysis.py', 'twinguard/twinguard_graph.py',
                 'twinguard/twinguard_gate.py', 'twinguard/twinguard_power_sim.py'],
    'harness': ['harness/'],
    'runner': ['runner/'],
    'generator': ['bank/generate.py', 'bank/generator_prompt.md', 'bank/paraphrase.py',
                  'bank/make_spec.py', 'bank/sectors.toml', 'bank/render.py',
                  'bank/admission.py', 'bank/semantic_audit.py', 'bank/manipulation_check.py',
                  'bank/generation_log.jsonl', 'bank/paraphrase_log.jsonl',
                  'bank/rejections.jsonl'],
    'spec': ['bank/spec_matrix.csv', 'bank/spec_matrix.csv.sha256'],
    'audits': ['bank/audits/'],
    'kernel': ['notebooks/pilot_l4/pilot_l4.py', 'notebooks/pilot_l4/kernel-metadata.json',
               'notebooks/build_kernel.py', 'notebooks/model_overlay/'],
}


def git(*args, binary=False):
    r = subprocess.run(['git', *args], cwd=ROOT, capture_output=True, check=True)
    return r.stdout if binary else r.stdout.decode().strip()


def files_at(commit, path):
    out = git('ls-tree', '-r', '--name-only', commit, '--', path)
    return [f for f in out.splitlines() if f and '__pycache__' not in f]


def blob_sha(commit, path):
    return hashlib.sha256(git('show', f'{commit}:{path}', binary=True)).hexdigest()


def hashed(commit, paths):
    res = {}
    for p in paths:
        fs = files_at(commit, p)
        if not fs:
            raise SystemExit(f'{p}: not tracked at {commit}')
        for f in fs:
            res[f] = blob_sha(commit, f)
    return dict(sorted(res.items()))


def templates(commit):
    """Per-template manifest: SHA-256 of every file, plus one digest over the template."""
    spec = list(csv.DictReader(io.StringIO(git('show', f'{commit}:bank/spec_matrix.csv'))))
    res = {}
    for row in spec:
        tid = row['template_id']
        fs = hashed(commit, [f'bank/templates/{tid}/'])
        digest = hashlib.sha256(''.join(f'{k}\0{v}\n' for k, v in fs.items()).encode()).hexdigest()
        res[tid] = {'split': row['split'], 'mechanism': row['mechanism'],
                    'family': row['family'], 'digest': digest, 'files': fs}
    return res


def k_rule(tpls):
    """9.3: K = 30 when every mechanism has its 10 confirmatory templates admitted."""
    k_m = {}
    for t in tpls.values():
        if t['split'] == 'confirmatory':
            k_m[t['mechanism']] = k_m.get(t['mechanism'], 0) + 1
    K = sum(k_m.values())
    return {'K': K, 'k_by_mechanism': dict(sorted(k_m.items())),
            'resource_mode': min(k_m.values() or [0]) < 10,
            'rule': '9.3: K = 30 if all 10 sectors have their three templates admitted; '
                    'min_m k_m < 10 -> resource mode, --exploratory'}


def s_rule(t_a, budget_hours, K):
    """9.3: T = K x 3 x 4 x S x t_a; the largest S in (4, 3, 2) with T <= 0.6 budget."""
    rows = []
    for S in (4, 3, 2):
        T = K * len(FRAMINGS) * PARAPHRASES * S * t_a / 3600
        rows.append({'S': S, 'T_hours': round(T, 2), 'fits': T <= 0.6 * budget_hours})
    chosen = next((r['S'] for r in rows if r['fits']), 2)
    return chosen, rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--commit', default='HEAD')
    ap.add_argument('--S', type=int, required=True, choices=(2, 3, 4))
    ap.add_argument('--t-a', type=float, required=True,
                    help='amortized seconds per run measured in the pilot (9.3)')
    ap.add_argument('--budget-hours', type=float, required=True,
                    help='GPU hours available for the confirmatory runs (9.3)')
    ap.add_argument('--justification', required=True)
    ap.add_argument('--pilot-sealed-sha256', default='')
    ap.add_argument('--environment-id', default='kaggle-L4x4|4 NVIDIA L4|img:37c64f7d|'
                    'vllm0.19.1|tp4|model:52f3f65-overlay')
    ap.add_argument('--out', default=str(ROOT / 'freeze' / 'manifest.json'))
    a = ap.parse_args(argv)

    commit = git('rev-parse', a.commit)
    # the schedule is computed by importing the runner from the working tree: it must BE the commit
    if commit != git('rev-parse', 'HEAD') or git('status', '--porcelain', '--untracked-files=no'):
        raise SystemExit('freeze from a clean checkout of the frozen commit (HEAD, no changes)')
    tpls = templates(commit)
    kr = k_rule(tpls)
    s_rule_S, s_rows = s_rule(a.t_a, a.budget_hours, kr['K'])
    if a.S != s_rule_S:
        raise SystemExit(f'--S {a.S} disagrees with the 9.3 rule, which gives S = {s_rule_S}: {s_rows}')

    sys.path.insert(0, str(ROOT))
    from runner.runner import schedule, run_seed  # noqa: E402  (same code as the commit)
    runs = schedule(ROOT / 'bank' / 'templates', ROOT / 'bank' / 'spec_matrix.csv',
                    'confirmatory', a.S, ORDER_SEED)
    order_digest = hashlib.sha256('\n'.join(r['run_id'] for r in runs).encode()).hexdigest()

    manifest = {
        'package': 'TwinGuard freeze (protocol 9.4)',
        'commit': commit,
        'commit_utc': git('show', '-s', '--format=%cI', commit),
        'model': {'id': 'google/gemma-4-31B-it-qat-w4a16-ct',
                  'revision': '52f3f65bc7a02d555763bc923bd1d9094898219d',
                  'kaggle_model': 'google/gemma-4/Other/gemma-4-31b-it-qat-w4a16-ct/2',
                  'chat_template_overlay': 'HF 52f3f65 chat_template.jinja + tokenizer_config.json'},
        'environment_id': a.environment_id,
        'sampling': SAMPLING,
        'reasoning': {'enable_thinking': True},
        'harness_limits': 'docs/harness.md (100 tool calls, 60 min per run)',
        'seeds': {'order_seed': ORDER_SEED,
                  'run_seed': 'sha256("<template_id>|p<paraphrase>|r<replicate>")[:8] & 0x7fffffff, '
                              'identical across framings',
                  'example': {'M1.cold_chain_release|p1|r1': run_seed('M1.cold_chain_release', 1, 1)}},
        'design': {**kr, 'S': a.S, 'framings': list(FRAMINGS), 'paraphrases': PARAPHRASES,
                   'scheduled_runs': len(runs), 'schedule_sha256': order_digest},
        'S_decision': {'t_a_seconds': a.t_a, 'budget_hours': a.budget_hours, 'rule_rows': s_rows,
                       'justification': a.justification},
        'pilot_sealed_sha256': a.pilot_sealed_sha256,
        'files': {g: hashed(commit, ps) for g, ps in GROUPS.items()},
        'templates': tpls,
    }
    text = json.dumps(manifest, indent=1, sort_keys=False) + '\n'
    out = Path(a.out)
    out.write_text(text)
    digest = hashlib.sha256(text.encode()).hexdigest()
    Path(str(out) + '.sha256').write_text(f'{digest}  {out.name}\n')
    print(json.dumps({'manifest': str(out), 'sha256': digest, 'K': kr['K'], 'S': a.S,
                      'scheduled_runs': len(runs)}))


if __name__ == '__main__':
    main()
