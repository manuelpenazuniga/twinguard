"""Build the freeze package of protocol 9.4 from one git commit (WP9).

Everything is read from the commit with `git show`, never from the working tree, so anyone
with the repo can rebuild the same manifest and hash:

  python freeze/make_freeze.py --S 4 --t-a 61.2 --budget-hours 30.1 --shards 2 \
      --deadline-utc 2026-11-10T15:00:00Z --justification "..." --pilot-sealed-sha256 ...

t_a and the budget follow docs/decisions.md D8, fixed before the pilot output was read.

Writes freeze/manifest.json and freeze/manifest.json.sha256. The SHA-256 is then stamped
with OpenTimestamps (`ots stamp freeze/manifest.json`), which is a separate, explicit step.
The manifest holds hashes and configuration only: no results and no competition data.
"""
import argparse
import calendar
import csv
import hashlib
import io
import json
import math
import subprocess
import sys
import time
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


MECHANISMS = ('M1', 'M2', 'M3')
K_PROTOCOL = 30                  # 9.3 uses the fixed 30 in T, not the admitted count


def admitted(commit, tid):
    """Admission = technical admission report passed (6.2) AND the last level-2 semantic audit
    of the template says pass (6.4) AND the Gemma manipulation check passed (6.5, WP7)."""
    try:
        tech = json.loads(git('show', f'{commit}:bank/admission/{tid}.json'))
    except subprocess.CalledProcessError:
        return False
    sem = None
    for line in git('show', f'{commit}:bank/audits/semantic_audit_level2.jsonl').splitlines():
        r = json.loads(line)
        if r.get('template_id') == tid and 'summary' in r:
            sem = r['summary'].get('verdict')
    wp7 = json.loads(git('show', f'{commit}:bank/audits/manipulation_check_provenance.json'))
    man = [r for r in wp7['results'] if r['template_id'] == tid]
    return bool(tech.get('technical_pass')) and sem == 'pass' and len(man) == 1 \
        and bool(man[0].get('pass')) and bool(man[0].get('complete'))


def k_rule(commit, tpls):
    """9.3: K = 30 if the 10 sectors have their three templates (one per mechanism) admitted,
    taking within each mechanism the first by creation order; min_m k_m < 10 -> resource
    mode (--exploratory). Missing mechanisms count as 0."""
    spec = list(csv.DictReader(io.StringIO(git('show', f'{commit}:bank/spec_matrix.csv'))))
    conf = sorted((r for r in spec if r['split'] == 'confirmatory'),
                  key=lambda r: int(r['creation_order']))
    ok = {r['template_id']: admitted(commit, r['template_id']) for r in conf}
    chosen = {m: [r for r in conf if r['mechanism'] == m and ok[r['template_id']]][:10]
              for m in MECHANISMS}
    k_m = {m: len(v) for m, v in chosen.items()}
    sectors = {}
    for v in chosen.values():
        for r in v:
            sectors.setdefault(r['family'], set()).add(r['mechanism'])
    complete = sorted(f for f, ms in sectors.items() if ms == set(MECHANISMS))
    selected = {r['template_id'] for v in chosen.values() for r in v}
    # the schedule takes EVERY confirmatory row of the spec: it must be exactly the selection
    unselected = sorted({r['template_id'] for r in conf} - selected)
    resource = min(k_m.values()) < 10 or len(complete) < 10 or bool(unselected)
    return {'K': sum(k_m.values()), 'k_by_mechanism': k_m, 'complete_sectors': len(complete),
            'not_admitted': sorted(t for t, a in ok.items() if not a),
            'scheduled_but_not_selected': unselected,
            'selected': {m: [r['template_id'] for r in v] for m, v in chosen.items()},
            'resource_mode': resource,
            'rule': '9.3: K = 30 if all 10 sectors have their three templates admitted '
                    '(first by creation order per mechanism); min_m k_m < 10 -> resource '
                    'mode, --exploratory'}


def s_rule(t_a, budget_hours):
    """9.3: T = 30 x 3 x 4 x S x t_a; S = 4 if T <= 0.6 budget, else 3, else 2 (declared)."""
    for v, name in ((t_a, 't_a'), (budget_hours, 'budget')):
        if not (isinstance(v, (int, float)) and math.isfinite(v) and v > 0):
            raise SystemExit(f'{name} must be a positive finite number, got {v!r}')
    rows = []
    for S in (4, 3, 2):
        T = K_PROTOCOL * len(FRAMINGS) * PARAPHRASES * S * t_a / 3600
        rows.append({'S': S, 'T_hours': round(T, 3), 'fits': T <= 0.6 * budget_hours})
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
    ap.add_argument('--shards', type=int, default=2, help='parallel kernels (D8)')
    ap.add_argument('--deadline-utc', required=True,
                    help='YYYY-MM-DDTHH:MM:SSZ: no confirmatory run starts after it (7.4 cut)')
    ap.add_argument('--pilot-sealed-sha256', default='')
    ap.add_argument('--environment-id', required=True,
                    help="exactly the runner's environment_id (pilot runs.csv column)")
    ap.add_argument('--out', default=str(ROOT / 'freeze' / 'manifest.json'))
    a = ap.parse_args(argv)

    commit = git('rev-parse', a.commit)
    # the schedule is computed by importing the runner from the working tree: it must BE the commit
    if commit != git('rev-parse', 'HEAD') or git('status', '--porcelain', '--untracked-files=no'):
        raise SystemExit('freeze from a clean checkout of the frozen commit (HEAD, no changes)')
    tpls = templates(commit)
    kr = k_rule(commit, tpls)
    if kr['resource_mode']:
        raise SystemExit(f'resource mode (9.3): {kr}')
    s_rule_S, s_rows = s_rule(a.t_a, a.budget_hours)
    deadline = calendar.timegm(time.strptime(a.deadline_utc, '%Y-%m-%dT%H:%M:%SZ'))
    if a.S != s_rule_S:
        raise SystemExit(f'--S {a.S} disagrees with the 9.3 rule, which gives S = {s_rule_S}: {s_rows}')

    sys.path.insert(0, str(ROOT))
    from runner.runner import (MODEL_ID, schedule, schedule_digest, shard_runs,  # noqa: E402
                               run_seed)       # same code as the commit (checked above)
    runs = schedule(ROOT / 'bank' / 'templates', ROOT / 'bank' / 'spec_matrix.csv',
                    'confirmatory', a.S, ORDER_SEED)
    blocks = []
    for r in runs:
        if not blocks or blocks[-1] != r['family']:
            blocks.append(r['family'])
    shards = {f'{i}/{a.shards}': shard_runs(runs, (i, a.shards)) for i in range(1, a.shards + 1)}

    manifest = {
        'package': 'TwinGuard freeze (protocol 9.4)',
        'commit': commit,
        'commit_utc': git('show', '-s', '--format=%cI', commit),
        'model': {'id': MODEL_ID,
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
                   'scheduled_runs': len(runs), 'schedule_sha256': schedule_digest(runs),
                   'block_order': blocks,
                   'shards': {k: {'blocks': [b for b in blocks if any(r['family'] == b for r in v)],
                                  'runs': len(v), 'schedule_sha256': schedule_digest(v)}
                              for k, v in shards.items()}},
        'confirmatory_deadline_utc': a.deadline_utc,
        'confirmatory_deadline_epoch': deadline,
        'truncation': '7.4: a run not started by the deadline gets an infra_failed row '
                      '(close-out); any scheduled block not complete -> --exploratory, with K '
                      'scheduled, K evaluable per contrast and the excluded blocks reported '
                      '(runner/merge.py)',
        'S_decision': {'t_a_seconds': a.t_a, 'budget_hours': a.budget_hours, 'rule_rows': s_rows,
                       'definitions': 'docs/decisions.md D8', 'justification': a.justification},
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
