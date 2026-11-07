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
    Path(work).mkdir(parents=True, exist_ok=True)
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
        subprocess.run(['chown', '-R', f'{eval_user}:{eval_user}', str(work)])
        Path(work).chmod(0o700)
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
class ConfigError(RuntimeError):
    """Wrong endpoint/model/manifest: abort the session, never retry or record as a run."""


def bank_hash(bank_dir, template_ids):
    h = hashlib.sha256()
    for tid in sorted(set(template_ids)):
        for p in sorted((Path(bank_dir) / tid).rglob('*')):
            if p.is_file() and '__pycache__' not in p.parts:
                h.update(str(p.relative_to(bank_dir)).encode() + b'\0' + p.read_bytes())
    return h.hexdigest()


def opaque(run_id, salt):
    """Directory name that reveals neither the study, the run nor the framing."""
    return 'w' + hashlib.sha256(f'{salt}|{run_id}'.encode()).hexdigest()[:16]


class Runner:
    def __init__(self, args, client=None):
        self.a = args
        self.out = Path(args.out)
        self.out.mkdir(parents=True, exist_ok=True)
        self.attempts = self.out / 'attempts.jsonl'
        self.lock = threading.Lock()
        self.client = client or OpenAICompatClient(args.base_url, args.model, timeout=900)
        if client is None:
            served = self._served_models()
            if args.model not in served:
                raise ConfigError(f'model {args.model!r} not served by {args.base_url}: {served}')
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
        self.salt = hashlib.sha256(f'{args.order_seed}|{args.code_commit}'.encode()).hexdigest()

    def _served_models(self):
        import urllib.request
        with urllib.request.urlopen(self.a.base_url.rstrip('/') + '/models', timeout=30) as r:
            return [m['id'] for m in json.loads(r.read())['data']]

    # -------------------------------------------------------------- persistence
    def records(self):
        if not self.attempts.exists():
            return []
        return [json.loads(l) for l in self.attempts.read_text(encoding='utf-8').splitlines()
                if l.strip()]

    def done(self):
        return {r['run_id']: r for r in self.records() if r.get('final')}

    def tries_started(self, run_id):
        return sum(1 for r in self.records() if r['run_id'] == run_id and r.get('event') == 'start')

    def log(self, rec):
        with self.lock, open(self.attempts, 'a', encoding='utf-8') as f:
            f.write(json.dumps(rec) + '\n')

    def check_manifest(self, runs):
        man = {'split': self.a.split, 'replicates': self.a.replicates,
               'order_seed': self.a.order_seed, 'code_commit': self.a.code_commit,
               'model': self.a.model, 'model_revision': self.a.model_revision,
               'environment_id': self.a.environment_id, 'budget': self.budget.as_dict(),
               'sampling': SAMPLING, 'contract_hash': C.contract_hash(),
               'bank_hash': bank_hash(self.a.bank, [r['template_id'] for r in runs]),
               'schedule_sha256': hashlib.sha256(json.dumps(
                   [(r['run_id'], r['seed'], r['order']) for r in runs]).encode()).hexdigest()}
        path = self.out / 'manifest.json'
        if path.exists():
            old = json.loads(path.read_text())
            if old != man:
                diff = sorted(k for k in man if old.get(k) != man[k])
                raise ConfigError(f'resume with a different configuration: {diff}')
        else:
            path.write_text(json.dumps(man, indent=1))
            (self.out / 'schedule.json').write_text(json.dumps(runs, indent=0))
        return man

    # -------------------------------------------------------------- one run
    def run_one(self, run):
        uid = self.uids.get()
        try:
            return self._run_one(run, uid)
        except ConfigError:
            raise
        except Exception as exc:   # controller failure: the run still gets its row
            row = self._row(run, 'infra_failed', None, None, None, None, {}, self.tries_started(run['run_id']))
            self.log({'run_id': run['run_id'], 'final': True, 'row': row,
                      'controller_error': f'{type(exc).__name__}: {exc}'[:500]})
            return row
        finally:
            self.uids.put(uid)

    def _row(self, run, status, W, F, M, crash, summary, tries):
        return {**{k: run[k] for k in ('run_id', 'template_id', 'family', 'mechanism', 'split',
                                       'framing', 'issue_paraphrase', 'replicate_id', 'seed')},
                'status': status, 'W': W, 'F': F, 'M': M, 'crash': crash,
                'model_id': MODEL_ID, 'model_revision': self.a.model_revision,
                'harness_commit': self.a.code_commit, 'oracle_commit': self.a.code_commit,
                'environment_id': self.a.environment_id, 'turns': summary.get('turns'),
                'tool_calls': summary.get('tool_calls_used'),
                'elapsed_seconds': summary.get('elapsed_seconds'),
                'termination': summary.get('termination'), 'attempts': tries}

    def _run_one(self, run, uid):
        tdir = Path(self.a.bank) / run['template_id']
        t, meta = load(tdir)
        base = Path(self.a.work) / opaque(run['run_id'], self.salt)
        tries = self.tries_started(run['run_id'])   # a crash mid-try already used that try
        summary, infra = {}, True
        while tries < 2:
            tries += 1
            work = base / f't{tries}'
            if work.exists():
                shutil.rmtree(work)
            root = render(tdir, run['framing'], work / 'workspace')
            ws = Workspace(root, work / 'tmp')          # baseline commit as the controller
            ws.init_baseline()
            if uid:
                subprocess.run(['chown', '-R', f'{uid}:{uid}', str(work)], check=True)
                base.chmod(0o711)
                work.chmod(0o700)
                ws.run_as = uid
            self.log({'run_id': run['run_id'], 'event': 'start', 'try': tries, 'uid': uid,
                      'utc': time.time()})
            t0 = time.time()
            try:
                summary = run_episode(task_for(meta, run['issue_paraphrase']), ws, self.client,
                                      self.budget,
                                      self.out / 'logs' / f"{run['run_id'].replace(':', '__')}.t{tries}.jsonl",
                                      {**SAMPLING, 'seed': run['seed']})
            finally:
                ws.kill_user_processes()
            self.log({'run_id': run['run_id'], 'event': 'end', 'try': tries,
                      'termination': summary['termination'], 'wall_s': round(time.time() - t0, 1)})
            if summary['termination'] == 'config_error':
                raise ConfigError(f"endpoint configuration error during {run['run_id']}")
            infra = summary['termination'] == 'infra_error'
            if not infra:
                break
        if infra:
            row = self._row(run, 'infra_failed', None, None, None, None, summary, tries)
            ev = None
        else:
            (self.out / 'patches').mkdir(exist_ok=True)
            (self.out / 'patches' / f"{run['run_id'].replace(':', '__')}.patch").write_text(
                summary['patch'] or '', encoding='utf-8')
            # evaluation lives OUTSIDE the agent's 0700 try directory
            ev = evaluate(tdir, run['framing'], summary['patch'], base / 'evaluation',
                          self.a.eval_user)
            status, W, F, M, crash = outcome(summary, ev)
            row = self._row(run, status, W, F, M, crash, summary, tries)
        self.log({'run_id': run['run_id'], 'final': True, 'row': row,
                  'patch_sha256': hashlib.sha256((summary.get('patch') or '').encode()).hexdigest(),
                  'evaluation': ev})
        if not self.a.keep_work:
            shutil.rmtree(base, ignore_errors=True)
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
        man = self.check_manifest(runs)
        done = self.done()
        todo = [r for r in runs if r['run_id'] not in done]
        # 7.4: confirmatory sector blocks are a barrier; the pilot is a single block
        blocks = []
        for r in todo:
            key = r['family'] if self.a.split == 'confirmatory' else 'all'
            if not blocks or blocks[-1][0] != key:
                blocks.append((key, []))
            blocks[-1][1].append(r)
        t0 = time.time()
        for _, block in blocks:
            with ThreadPoolExecutor(self.a.concurrency) as ex:
                for _ in ex.map(self.run_one, block):
                    self.write_csv()
        n = self.write_csv()
        meta = {'scheduled': len(runs), 'completed': n, 'ran_now': len(todo),
                'wall_seconds_this_session': round(time.time() - t0, 1),
                'concurrency': self.a.concurrency, 'manifest': man}
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
    ap.add_argument('--base-url', required=True)
    ap.add_argument('--model', required=True)
    ap.add_argument('--model-revision', required=True,
                    help='revision verified by hashing the served files (kernel phase 7)')
    ap.add_argument('--concurrency', type=int, default=8)
    ap.add_argument('--budget-json', default='')
    ap.add_argument('--run-as', default=None,
                    help='comma-separated unprivileged uids, one per concurrency slot')
    ap.add_argument('--eval-user', default=None)
    ap.add_argument('--allow-unisolated', action='store_true',
                    help='development only: run without unprivileged uids')
    ap.add_argument('--environment-id', required=True)
    ap.add_argument('--code-commit', required=True)
    ap.add_argument('--limit', type=int, default=0, help='run only the first N scheduled (smoke)')
    ap.add_argument('--keep-work', action='store_true')
    a = ap.parse_args(argv)
    if not a.allow_unisolated and not (a.run_as and a.eval_user):
        raise SystemExit('refusing to run without --run-as and --eval-user (isolation)')
    if a.run_as and len(a.run_as.split(',')) < a.concurrency:
        raise SystemExit('need one --run-as uid per concurrency slot')
    runs = schedule(a.bank, a.spec, a.split, a.replicates, a.order_seed)
    if a.limit:
        runs = runs[:a.limit]
    print(json.dumps(Runner(a).run(runs)))


if __name__ == '__main__':
    main()
