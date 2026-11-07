"""WP8/WP10 runner: scheduled agent runs -> one Annex A row per scheduled run.

Design (protocol 7.3-7.5, 8.1-8.3, 9.1, Annex A; Astra operational advice 2026-11-06):
  * The schedule is deterministic and fixed before any run: run_id, seed and order come from
    the template list, S, and a published order seed. Seeds differ between replicates and
    are identical across framings for the same template, paraphrase and replicate.
  * Every attempt is appended to an immutable attempts.jsonl; a run is complete once it has a
    final record. Restarting the runner skips completed run_ids (resume without duplicates).
  * One retry only for verifiable infrastructure failures (endpoint unreachable/5xx after the
    client retries), identified without looking at W. Otherwise `infra_failed` (W/F/M empty).
  * Evaluation never trusts the agent's sandbox: the submitted patch is applied to a clean
    render of the same framing; visible tests give F, the behavioural oracle gives W/crash.
    With `exec_prefix`, candidate code runs as an unprivileged evaluation uid.
  * Status (8.3): budget_exhausted > patch (M=1) > no_patch (M=0). crash => W=F=0.
    Oracle evaluator failure => indeterminate (W/F/M/crash empty).

Usage (Kaggle, after vLLM is up):
  python runner/runner.py --split pilot --replicates 1 --out results/pilot \
      --base-url http://127.0.0.1:8000/v1 --model <served id> --concurrency 8 \
      --environment-id <id> --code-commit <sha>
"""
import argparse
import csv
import hashlib
import json
import random
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
for p in (str(ROOT), str(ROOT / 'twinguard')):
    if p not in sys.path:
        sys.path.insert(0, p)

from bank import admission  # noqa: E402
from bank.render import FRAMINGS, load, render, task_for  # noqa: E402
from harness import contract as C  # noqa: E402
from harness.loop import OpenAICompatClient, run_episode  # noqa: E402
from harness.workspace import Workspace, strip_protected_files_from_patch  # noqa: E402

# Same string as twinguard_analysis.py --model default (HF canonical spelling is 31B; '31b'
# resolves to the same repository).
MODEL_ID = 'google/gemma-4-31b-it-qat-w4a16-ct'
MODEL_REVISION = '52f3f65bc7a02d555763bc923bd1d9094898219d'
SAMPLING = {'temperature': 1.0, 'top_p': 0.95, 'top_k': 64, 'enable_thinking': True}
PARAPHRASES = 4
COLUMNS = ['run_id', 'template_id', 'family', 'mechanism', 'split', 'framing',
           'issue_paraphrase', 'replicate_id', 'seed', 'status', 'W', 'F', 'M', 'crash',
           'model_id', 'model_revision', 'harness_commit', 'oracle_commit', 'environment_id',
           'turns', 'tool_calls', 'elapsed_seconds', 'termination', 'attempts']


# ------------------------------------------------------------------ schedule
def run_seed(template_id, paraphrase, replicate):
    """Deterministic 31-bit seed; independent of the framing by construction."""
    h = hashlib.sha256(f'{template_id}|p{paraphrase}|r{replicate}'.encode()).hexdigest()
    return int(h[:8], 16) & 0x7FFFFFFF


def schedule(bank_dir, spec_csv, split, replicates, order_seed):
    rows = [r for r in csv.DictReader(open(spec_csv, encoding='utf-8')) if r['split'] == split]
    runs = []
    for r in rows:
        tdir = Path(bank_dir) / r['template_id']
        if not (tdir / 'template.json').exists():
            continue
        for p in range(1, PARAPHRASES + 1):
            for rep in range(1, replicates + 1):
                for f in FRAMINGS:
                    runs.append({'run_id': f"{split}:{r['template_id']}:{f}:p{p}:r{rep}",
                                 'template_id': r['template_id'], 'family': r['family'],
                                 'mechanism': r['mechanism'], 'split': split, 'framing': f,
                                 'issue_paraphrase': p, 'replicate_id': rep,
                                 'seed': run_seed(r['template_id'], p, rep)})
    rng = random.Random(order_seed)
    if split == 'confirmatory':
        # 7.4: one block per sector in random order; cells interleaved at random inside
        fams = sorted({r['family'] for r in runs})
        rng.shuffle(fams)
        ordered = []
        for fam in fams:
            block = [r for r in runs if r['family'] == fam]
            rng.shuffle(block)
            ordered += block
        runs = ordered
    else:
        rng.shuffle(runs)
    for i, r in enumerate(runs, 1):
        r['order'] = i
    return runs


# ------------------------------------------------------------------ evaluation
def evaluate(template_dir, framing, patch, work, eval_user=None):
    """Apply the patch to a clean render; F from visible tests, W/crash from the oracle.
    With eval_user, the candidate code is imported only by that unprivileged uid."""
    ws = Path(work) / 'eval'
    if ws.exists():
        shutil.rmtree(ws)
    render(template_dir, framing, ws)
    admission.init_repo(ws)
    patch = strip_protected_files_from_patch(patch or '')
    M = int(bool(patch.strip()))
    if M:
        pf = Path(work) / 'final.patch'
        pf.write_text(patch, encoding='utf-8')
        ok, err = admission.apply_patch(ws, pf)
        if not ok:   # a patch that does not apply leaves the code unchanged: record it
            return {'M': M, 'apply_error': err, 'tests': None, 'oracle': None}
    if eval_user:
        subprocess.run(['chown', '-R', f'{eval_user}:{eval_user}', str(ws)])
    tests = admission.run_tests(ws)
    oracle = admission.run_oracle(template_dir, ws)
    return {'M': M, 'tests': tests, 'oracle': oracle}


def outcome(summary, ev):
    """Map an episode summary + evaluation to (status, W, F, M, crash)."""
    if ev is None or ev.get('oracle') is None and ev.get('apply_error') is None:
        return 'indeterminate', None, None, None, None
    if ev.get('apply_error'):
        return 'indeterminate', None, None, None, None
    o = ev['oracle']
    if 'oracle_error' in o:
        return 'indeterminate', None, None, None, None
    M = ev['M']
    crash = int(bool(o['crash']))
    W = 0 if (crash or not M) else int(o['W'])
    F = 0 if (crash or not M) else int(ev['tests']['passed'])
    status = 'budget_exhausted' if summary.get('budget_exhausted') else \
        ('patch' if M else 'no_patch')
    return status, W, F, M, crash


# ------------------------------------------------------------------ runner
class Runner:
    def __init__(self, args, client=None):
        self.a = args
        self.out = Path(args.out)
        self.out.mkdir(parents=True, exist_ok=True)
        self.attempts = self.out / 'attempts.jsonl'
        self.lock = threading.Lock()
        self.client = client or OpenAICompatClient(args.base_url, args.model, timeout=900)
        self.budget = C.Budget(**json.loads(args.budget_json or '{}'))
        # One unprivileged uid per concurrency slot, so concurrent runs (possibly other
        # framings of the same template) can never read each other's workspaces.
        import queue
        self.uids = queue.Queue()
        for u in (args.run_as.split(',') if args.run_as else [None] * args.concurrency):
            self.uids.put(u)
        if args.eval_user:
            admission.EXEC_PREFIX = ['setpriv', f'--reuid={args.eval_user}',
                                     f'--regid={args.eval_user}', '--clear-groups',
                                     '--no-new-privs', '--']

    def done(self):
        if not self.attempts.exists():
            return {}
        final = {}
        for line in self.attempts.read_text(encoding='utf-8').splitlines():
            rec = json.loads(line)
            if rec.get('final'):
                final[rec['run_id']] = rec
        return final

    def log(self, rec):
        with self.lock, open(self.attempts, 'a', encoding='utf-8') as f:
            f.write(json.dumps(rec) + '\n')

    def run_one(self, run):
        uid = self.uids.get()
        try:
            return self._run_one(run, uid)
        finally:
            self.uids.put(uid)

    def _run_one(self, run, uid):
        tdir = Path(self.a.bank) / run['template_id']
        t, meta = load(tdir)
        tries = 0
        while True:
            tries += 1
            work = Path(self.a.work) / run['run_id'].replace(':', '__') / f'try{tries}'
            if work.exists():
                shutil.rmtree(work)
            root = render(tdir, run['framing'], work / 'workspace')
            ws = Workspace(root, work / 'tmp', run_as=uid)
            ws.init_baseline()
            if uid:
                subprocess.run(['chown', '-R', f'{uid}:{uid}', str(work)])
                (work.parent).chmod(0o711)
                work.chmod(0o700)
            t0 = time.time()
            try:
                summary = run_episode(task_for(meta, run['issue_paraphrase']), ws, self.client,
                                      self.budget, self.out / 'logs' / f"{run['run_id'].replace(':', '__')}.try{tries}.jsonl",
                                      {**SAMPLING, 'seed': run['seed']})
            finally:
                ws.kill_user_processes()
            infra = summary['termination'] == 'infra_error'
            self.log({'run_id': run['run_id'], 'try': tries, 'final': False,
                      'termination': summary['termination'], 'wall_s': round(time.time() - t0, 1)})
            if infra and tries < 2:
                continue
            break
        if infra:
            status, W, F, M, crash, ev = 'infra_failed', None, None, None, None, None
        else:
            ev = evaluate(tdir, run['framing'], summary['patch'], work, self.a.eval_user)
            status, W, F, M, crash = outcome(summary, ev)
        row = {**{k: run[k] for k in ('run_id', 'template_id', 'family', 'mechanism', 'split',
                                      'framing', 'issue_paraphrase', 'replicate_id', 'seed')},
               'status': status, 'W': W, 'F': F, 'M': M, 'crash': crash,
               'model_id': MODEL_ID, 'model_revision': MODEL_REVISION,
               'harness_commit': self.a.code_commit, 'oracle_commit': self.a.code_commit,
               'environment_id': self.a.environment_id, 'turns': summary['turns'],
               'tool_calls': summary['tool_calls_used'],
               'elapsed_seconds': summary['elapsed_seconds'],
               'termination': summary['termination'], 'attempts': tries}
        self.log({'run_id': run['run_id'], 'final': True, 'row': row,
                  'patch_sha256': hashlib.sha256((summary['patch'] or '').encode()).hexdigest(),
                  'evaluation': ev})
        (self.out / 'patches').mkdir(exist_ok=True)
        (self.out / 'patches' / f"{run['run_id'].replace(':', '__')}.patch").write_text(
            summary['patch'] or '', encoding='utf-8')
        if not self.a.keep_work:
            shutil.rmtree(Path(self.a.work) / run['run_id'].replace(':', '__'), ignore_errors=True)
        return row

    def write_csv(self):
        rows = sorted((r['row'] for r in self.done().values()), key=lambda r: r['run_id'])
        with open(self.out / 'runs.csv', 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=COLUMNS)
            w.writeheader()
            for r in rows:
                w.writerow({k: ('' if r.get(k) is None else r.get(k)) for k in COLUMNS})
        return len(rows)

    def run(self, runs):
        done = self.done()
        todo = [r for r in runs if r['run_id'] not in done]
        (self.out / 'schedule.json').write_text(json.dumps(runs, indent=0))
        t0 = time.time()
        with ThreadPoolExecutor(self.a.concurrency) as ex:
            for _ in ex.map(self.run_one, todo):
                self.write_csv()
        n = self.write_csv()
        meta = {'scheduled': len(runs), 'completed': n, 'ran_now': len(todo),
                'wall_seconds_this_session': round(time.time() - t0, 1),
                'concurrency': self.a.concurrency}
        (self.out / 'session_summary.json').write_text(json.dumps(meta, indent=1))
        return meta


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--split', choices=('pilot', 'confirmatory'), required=True)
    ap.add_argument('--replicates', type=int, default=1)
    ap.add_argument('--order-seed', type=int, default=20261107)
    ap.add_argument('--bank', default=str(ROOT / 'bank' / 'templates'))
    ap.add_argument('--spec', default=str(ROOT / 'bank' / 'spec_matrix.csv'))
    ap.add_argument('--out', required=True)
    ap.add_argument('--work', default='/tmp/twinguard_work')
    ap.add_argument('--base-url')
    ap.add_argument('--model')
    ap.add_argument('--concurrency', type=int, default=8)
    ap.add_argument('--budget-json', default='')
    ap.add_argument('--run-as', default=None,
                    help='comma-separated unprivileged uids, one per concurrency slot')
    ap.add_argument('--eval-user', default=None)
    ap.add_argument('--environment-id', required=True)
    ap.add_argument('--code-commit', required=True)
    ap.add_argument('--limit', type=int, default=0, help='run only the first N scheduled (smoke)')
    ap.add_argument('--keep-work', action='store_true')
    a = ap.parse_args(argv)
    if a.run_as and len(a.run_as.split(',')) < a.concurrency:
        raise SystemExit('need one --run-as uid per concurrency slot')
    runs = schedule(a.bank, a.spec, a.split, a.replicates, a.order_seed)
    if a.limit:
        runs = runs[:a.limit]
    print(json.dumps(Runner(a).run(runs)))


if __name__ == '__main__':
    main()
