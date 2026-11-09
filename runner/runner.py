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
    Oracle evaluator failure or a non-applicable patch => needs blind adjudication
    (runner/adjudicate.py); unresolved => indeterminate (W/F/M/crash empty).
  * Resume: `episode_done` (with the patch saved first) means the agent never runs again for
    that run_id; two started tries without it => infra_failed. Events are fsync'ed.

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


def schedule(bank_dir, spec_csv, split, replicates, order_seed, only_template=None,
             only_paraphrase=0, first_replicate=1, max_paraphrase=0, framings=None):
    """max_paraphrase and framings exist only for the exploratory plan D12 (added after the
    freeze); their defaults (0, None) give exactly the frozen schedule."""
    arms = tuple(framings) if framings else FRAMINGS
    if not set(arms) <= set(FRAMINGS) or len(set(arms)) != len(arms):
        raise ValueError(f'bad framings {framings!r}')
    rows = [r for r in csv.DictReader(open(spec_csv, encoding='utf-8')) if r['split'] == split]
    if only_template:
        rows = [r for r in rows if r['template_id'] == only_template]
    runs = []
    for r in rows:
        tdir = Path(bank_dir) / r['template_id']
        if not (tdir / 'template.json').exists():
            raise FileNotFoundError(f"scheduled template missing from the bank: {tdir}")
        for p in range(1, PARAPHRASES + 1):
            if only_paraphrase and p != only_paraphrase:
                continue
            if max_paraphrase and p > max_paraphrase:
                continue
            for rep in range(first_replicate, first_replicate + replicates):
                for f in (f for f in FRAMINGS if f in arms):
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


def schedule_digest(runs):
    """One digest of a schedule (run_id, seed, global order), shared with the freeze manifest."""
    return hashlib.sha256(json.dumps(
        [(r['run_id'], r['seed'], r['order']) for r in runs]).encode()).hexdigest()


def parse_shard(text):
    """'i/N' -> (i, N) with 1 <= i <= N; '' -> None."""
    if not text:
        return None
    i, _, n = text.partition('/')
    i, n = int(i), int(n)
    if not 1 <= i <= n:
        raise ValueError(f'bad shard {text!r}')
    return i, n


def shard_runs(runs, shard):
    """Parallel sessions (two Kaggle kernels at once): sector blocks are dealt in the published
    order, block j (0-based) to shard j % N + 1. Each shard runs its blocks in that same order,
    so a time cut removes the LAST blocks of the published order in every shard. The global
    `order` is kept."""
    if shard is None:
        return runs
    i, n = shard
    fams = []
    for r in runs:
        if not fams or fams[-1] != r['family']:
            if r['family'] in fams:
                raise ValueError('sector blocks are not contiguous: cannot shard')
            fams.append(r['family'])
    mine = {f for j, f in enumerate(fams) if j % n == i - 1}
    return [r for r in runs if r['family'] in mine]


# ------------------------------------------------------------------ evaluation
def setpriv(user):
    """Run as `user` with umask 077 (files it creates are private to it)."""
    return ['setpriv', f'--reuid={user}', f'--regid={user}', '--clear-groups',
            '--no-new-privs', '--', '/bin/sh', '-c', 'umask 077; exec "$@"', 'sh']


def purge_user(user, keep=None):
    """Kill every process of `user` and delete what it left in shared scratch areas
    (except under `keep`, the work dir kept for debugging)."""
    subprocess.run(['pkill', '-KILL', '-u', user], capture_output=True)
    cmd = ['find', '/tmp', '/var/tmp', '/dev/shm', '-xdev', '-user', user]
    if keep:
        cmd += ['-not', '-path', f'{Path(keep).resolve()}/*']
    subprocess.run(cmd + ['-delete'], capture_output=True)


def evaluate(template_dir, framing, patch, work, eval_user=None):
    """F from the visible tests, W/crash from the oracle, each on its OWN fresh render of the
    patched code. Stages run one after the other as the slot's evaluator uid, and a stage's
    directory stays root-only until its turn, so candidate code running in one stage can
    never touch the other. The oracle is a root-owned, read-only copy (group = evaluator)."""
    work = Path(work)
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    work.chmod(0o711)
    patch = strip_protected_files_from_patch(patch or '')
    M = int(bool(patch.strip()))
    pf = None
    if M:
        pf = work / 'final.patch'
        pf.write_text(patch, encoding='utf-8')
        pf.chmod(0o600)
    stages = {}
    for name in ('o', 't'):
        st = work / name
        render(template_dir, framing, st / 'eval')
        admission.init_repo(st / 'eval')
        if pf is not None:
            ok, err = admission.apply_patch(st / 'eval', pf)
            if not ok:   # the agent's own diff should apply to a clean render: adjudicate
                return {'M': M, 'apply_error': err, 'tests': None, 'oracle': None}
        (st / 'scratch').mkdir()
        st.chmod(0o700)
        stages[name] = st
    tpl = work / 'tpl'
    shutil.copytree(Path(template_dir) / 'oracle', tpl / 'oracle')
    if eval_user:
        subprocess.run(['chown', '-R', f'root:{eval_user}', str(tpl)], check=True)
        subprocess.run(['chmod', '-R', 'u=rwX,g=rX,o=', str(tpl)], check=True)

    def stage(name, fn):
        st = stages[name]
        prefix = None
        if eval_user:
            subprocess.run(['chown', '-R', f'{eval_user}:{eval_user}', str(st)], check=True)
            prefix = setpriv(eval_user)
        try:
            return fn(st, prefix)
        finally:
            if eval_user:
                purge_user(eval_user)
    oracle = stage('o', lambda st, pre: admission.run_oracle(tpl, st / 'eval', pre, st / 'scratch'))
    tests = stage('t', lambda st, pre: admission.run_tests(st / 'eval', pre, st / 'scratch'))
    return {'M': M, 'tests': tests, 'oracle': oracle}


def needs_adjudication(ev):
    """Evaluator could not decide (oracle error / patch not applicable): 8.3 blind
    adjudication before the row may become `indeterminate`."""
    return bool(ev and (ev.get('apply_error') or (ev.get('oracle') or {}).get('oracle_error')))


def outcome(summary, ev, adjudication=None):
    """Map an episode summary + evaluation (+ blind adjudication) to (status, W, F, M, crash)."""
    status_eval = 'budget_exhausted' if summary.get('budget_exhausted') else None
    if ev is None:
        return 'indeterminate', None, None, None, None
    if needs_adjudication(ev):
        if not adjudication or not adjudication.get('resolved'):
            return 'indeterminate', None, None, None, None
        M = ev['M']
        crash = int(bool(adjudication['crash']))
        W = 0 if (crash or not M) else int(adjudication['W'])
        F = 0 if (crash or not M) else int(adjudication['F'])
        return status_eval or ('patch' if M else 'no_patch'), W, F, M, crash
    o = ev['oracle']
    M = ev['M']
    crash = int(bool(o['crash']))
    W = 0 if (crash or not M) else int(o['W'])
    F = 0 if (crash or not M) else int(ev['tests']['passed'])
    return status_eval or ('patch' if M else 'no_patch'), W, F, M, crash


# ------------------------------------------------------------------ runner
class ConfigError(RuntimeError):
    """Wrong endpoint/model/manifest: abort the session, never retry or record as a run."""


class ServerDown(ConfigError):
    """The model server stopped answering: abort the session instead of spending the
    remaining runs' tries on a dead endpoint (the next session resumes them)."""


class Deferred(Exception):
    """Session deadline reached before a (re)try could start: the run stays open and is
    resumed by the next session (no final record)."""


def write_durable(path, text):
    import os
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


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


def check_users(agents, evals):
    """Every slot needs its own unprivileged agent uid and evaluator uid; all distinct."""
    import pwd
    if len(agents) != len(evals):
        raise SystemExit('need as many --eval-user as --run-as uids (one pair per slot)')
    uids = {}
    for name in agents + evals:
        try:
            uid = pwd.getpwnam(name).pw_uid
        except KeyError:
            raise SystemExit(f'user {name!r} does not exist') from None
        if uid == 0:
            raise SystemExit(f'user {name!r} is root')
        uids[name] = uid
    if len(set(uids.values())) != len(agents) + len(evals):
        raise SystemExit('agent and evaluator users must be distinct uids')
    return uids


def slim(summary):
    return {k: v for k, v in summary.items() if k != 'patch'}


class Runner:
    def __init__(self, args, client=None):
        self.a = args
        self.out = Path(args.out)
        self.out.mkdir(parents=True, exist_ok=True)
        self.attempts = self.out / 'attempts.jsonl'
        self.lock = threading.Lock()
        self.halt = threading.Event()     # set on ServerDown: no further run starts
        self.client = client or (None if getattr(args, 'close_out', False) else
                                 OpenAICompatClient(args.base_url, args.model, timeout=900))
        self.served = None
        if client is None and getattr(args, 'close_out', False):
            self.client = None          # close-out never calls the model
        elif client is None:
            served = self.client.models()['data']
            if args.model not in [m['id'] for m in served]:
                raise ConfigError(f'model {args.model!r} not served by {args.base_url}: {served}')
            self.served = [{k: m.get(k) for k in ('id', 'root', 'max_model_len')} for m in served]
        self.budget = C.Budget(**json.loads(args.budget_json or '{}'))
        # One (agent uid, evaluator uid) pair per concurrency slot: concurrent runs and
        # evaluations (possibly other framings of the same template) never share a uid.
        import queue
        self.slots = queue.Queue()
        agents = args.run_as.split(',') if args.run_as else [None] * args.concurrency
        evals = args.eval_user.split(',') if args.eval_user else [None] * len(agents)
        for pair in zip(agents, evals):
            self.slots.put(pair)
        self.salt = hashlib.sha256(f'{args.order_seed}|{args.code_commit}'.encode()).hexdigest()
        self.stop_at = getattr(args, 'stop_at', 0) or 0
        self.skipped = 0

    # -------------------------------------------------------------- persistence
    def records(self):
        """All logged events. A truncated LAST line (crash mid-write) is ignored;
        corruption anywhere else aborts."""
        with self.lock:
            if not self.attempts.exists():
                return []
            lines = self.attempts.read_text(encoding='utf-8').split('\n')
        out = []
        for i, l in enumerate(lines):
            if not l.strip():
                continue
            try:
                out.append(json.loads(l))
            except json.JSONDecodeError:
                if i >= len(lines) - 2:   # the last non-empty line
                    break
                raise ConfigError(f'attempts.jsonl corrupt at line {i + 1}')
        return out

    def done(self):
        return {r['run_id']: r for r in self.records() if r.get('final')}

    def tries_started(self, run_id):
        return sum(1 for r in self.records() if r['run_id'] == run_id and r.get('event') == 'start')

    def log(self, rec):
        import os
        with self.lock:
            # a previous crash may have left a partial last line: that event never
            # happened (it was not durable), so it is cut before appending
            if self.attempts.exists() and self.attempts.stat().st_size:
                data = self.attempts.read_bytes()
                if not data.endswith(b'\n'):
                    with open(self.attempts, 'r+b') as f:
                        f.truncate(data.rfind(b'\n') + 1)
            with open(self.attempts, 'ab') as f:
                f.write(json.dumps(rec).encode() + b'\n')
                f.flush()
                os.fsync(f.fileno())

    def check_manifest(self, runs, offline=False):
        man = {'split': self.a.split, 'replicates': self.a.replicates,
               'order_seed': self.a.order_seed, 'code_commit': self.a.code_commit,
               'model': self.a.model, 'model_id': MODEL_ID,
               'model_revision': self.a.model_revision, 'served': self.served,
               'concurrency': self.a.concurrency,
               'environment_id': self.a.environment_id, 'budget': self.budget.as_dict(),
               'sampling': SAMPLING, 'contract_hash': C.contract_hash(),
               'bank_hash': bank_hash(self.a.bank, [r['template_id'] for r in runs]),
               'shard': getattr(self.a, 'shard', '') or '',
               'schedule_sha256': schedule_digest(runs)}
        path = self.out / 'manifest.json'
        if not path.exists() and (self.attempts.exists() or (self.out / 'episodes').exists()):
            # records without the manifest that produced them: never adopt them silently
            raise ConfigError('results exist without manifest.json: refusing to resume')
        if path.exists():
            old = json.loads(path.read_text())
            if offline:   # close-out without a server: the served model is not re-checked
                man['served'] = old.get('served')
            if old != man:
                diff = sorted(k for k in man if old.get(k) != man[k])
                raise ConfigError(f'resume with a different configuration: {diff}')
        else:
            path.write_text(json.dumps(man, indent=1))
            (self.out / 'schedule.json').write_text(json.dumps(runs, indent=0))
        return man

    def adjudications(self):
        """Blind adjudications (runner/adjudicate.py): last decision per run_id wins."""
        path = self.out / 'adjudications.jsonl'
        if not path.exists():
            return {}
        out = {}
        for l in path.read_text(encoding='utf-8').splitlines():
            if l.strip():
                d = json.loads(l)
                out[d['run_id']] = d
        return out

    # -------------------------------------------------------------- one run
    def run_one(self, run, ignore_deadline=False):
        if (self.stop_at and time.time() > self.stop_at and not ignore_deadline) or \
                self.halt.is_set():
            self.skipped += 1          # not started: no event, resumable in the next session
            return None
        agent, evaluator = self.slots.get()
        base = Path(self.a.work) / opaque(run['run_id'], self.salt)
        try:
            return self._run_one(run, agent, evaluator, base)
        except ConfigError:
            raise
        except Deferred:
            self.skipped += 1
            return None
        except Exception as exc:   # controller failure: the run still gets its row
            row = self._row(run, 'infra_failed', None, None, None, None, {},
                            self.tries_started(run['run_id']))
            self.log({'run_id': run['run_id'], 'final': True, 'row': row,
                      'controller_error': f'{type(exc).__name__}: {exc}'[:500]})
            return row
        finally:
            for u in (agent, evaluator):
                if u:
                    purge_user(u, self.a.work if self.a.keep_work else None)
            if not self.a.keep_work:
                shutil.rmtree(base, ignore_errors=True)
            self.slots.put((agent, evaluator))

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

    def _patch_path(self, run):
        return self.out / 'patches' / f"{run['run_id'].replace(':', '__')}.patch"

    def _checkpoint_path(self, run):
        return self.out / 'episodes' / f"{run['run_id'].replace(':', '__')}.json"

    def _repair_patch(self, run, patch):
        """The checkpoint is authoritative: (re)write the .patch if missing or different."""
        pp = self._patch_path(run)
        if not pp.exists() or pp.read_text(encoding='utf-8') != patch:
            write_durable(pp, patch)

    def _checkpoint(self, run):
        p = self._checkpoint_path(run)
        return json.loads(p.read_text(encoding='utf-8')) if p.exists() else None

    def _episode(self, run, agent, base):
        """Run the agent (at most two tries, the second only after verifiable infrastructure
        failure). Returns (summary, tries, infra). Resumes: an episode already recorded as
        done is never run again."""
        recs = [r for r in self.records() if r['run_id'] == run['run_id']]
        tries = sum(1 for r in recs if r.get('event') == 'start')
        ck = self._checkpoint(run)
        if ck is not None:          # the agent already finished: never run it again
            self._repair_patch(run, ck['summary'].get('patch') or '')
            return ck['summary'], ck['tries'], False
        tdir = Path(self.a.bank) / run['template_id']
        t, meta = load(tdir)
        summary, infra = {}, True
        while tries < 2:
            if self.stop_at and time.time() > self.stop_at:
                raise Deferred(run['run_id'])
            tries += 1
            work = base / f't{tries}'
            if work.exists():
                shutil.rmtree(work)
            root = render(tdir, run['framing'], work / 'workspace')
            ws = Workspace(root, work / 'tmp')          # baseline commit as the controller
            ws.init_baseline()
            if agent:
                subprocess.run(['chown', '-R', f'{agent}:{agent}', str(work)], check=True)
                base.chmod(0o711)
                work.chmod(0o700)
                ws.run_as = agent
            self.log({'run_id': run['run_id'], 'event': 'start', 'try': tries, 'uid': agent,
                      'concurrency': self.a.concurrency, 'utc': time.time()})
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
            self._require_server(run)
        if not infra:
            # ONE durable file (summary + patch): written atomically before the event, so a
            # crash at any point either has it (episode recovered) or not (try counted)
            write_durable(self._checkpoint_path(run),
                          json.dumps({'summary': summary, 'tries': tries}))
            write_durable(self._patch_path(run), summary['patch'] or '')
            self.log({'run_id': run['run_id'], 'event': 'episode_done', 'try': tries,
                      'summary': slim(summary),
                      'patch_sha256': hashlib.sha256((summary['patch'] or '').encode()).hexdigest()})
        return summary, tries, infra

    def _require_server(self, run):
        """After an infrastructure failure: if the server itself is gone, stop the session
        (no final row; the started try stays counted) rather than fail every remaining run."""
        probe = getattr(self.client, 'models', None)
        if probe is None:
            return
        try:
            probe()
        except Exception as exc:
            self.halt.set()            # queued runs of this block must not start
            raise ServerDown(f"model server unreachable after {run['run_id']}: "
                             f"{type(exc).__name__}") from exc

    def _run_one(self, run, agent, evaluator, base):
        tries_before = self.tries_started(run['run_id'])
        if tries_before >= 2 and self._checkpoint(run) is None:
            # both tries were spent by crashed sessions: infrastructure, no third episode
            summary, tries, infra = {}, tries_before, True
        else:
            summary, tries, infra = self._episode(run, agent, base)
        if infra:
            row = self._row(run, 'infra_failed', None, None, None, None, summary, tries)
            ev = None
        else:
            tdir = Path(self.a.bank) / run['template_id']
            ev = evaluate(tdir, run['framing'], summary['patch'], base / 'evaluation', evaluator)
            status, W, F, M, crash = outcome(summary, ev)
            row = self._row(run, status, W, F, M, crash, summary, tries)
        self.log({'run_id': run['run_id'], 'final': True, 'row': row,
                  'summary': slim(summary) if summary else None,
                  'needs_adjudication': needs_adjudication(ev),
                  'patch_sha256': hashlib.sha256((summary.get('patch') or '').encode()).hexdigest(),
                  'evaluation': ev})
        return row

    def rows(self):
        """Final rows with blind adjudications applied (8.3)."""
        adj = self.adjudications()
        out = []
        for rid, rec in self.done().items():
            row = dict(rec['row'])
            if rec.get('needs_adjudication') and rid in adj:
                status, W, F, M, crash = outcome(rec.get('summary') or {}, rec['evaluation'],
                                                 adj[rid])
                row.update(status=status, W=W, F=F, M=M, crash=crash)
            out.append(row)
        return sorted(out, key=lambda r: r['run_id'])

    def pending_adjudication(self):
        """Runs that need blind adjudication and have no decision yet (a decision that the
        run cannot be resolved also counts as decided)."""
        adj = self.adjudications()
        return sorted(rid for rid, r in self.done().items()
                      if r.get('needs_adjudication') and rid not in adj)

    def write_summary(self, runs, extra=None):
        meta = {'scheduled': len(runs), 'completed': len(self.done()),
                'needs_adjudication': len(self.pending_adjudication()),
                'concurrency': self.a.concurrency, **(extra or {})}
        old = self.out / 'session_summary.json'
        if old.exists():
            import os
            hist = self.out / 'session_history.jsonl'
            with open(hist, 'a', encoding='utf-8') as f:
                f.write(old.read_text().replace('\n', ' ') + '\n')
                f.flush()
                os.fsync(f.fileno())
        write_durable(old, json.dumps(meta, indent=1))
        return meta

    def write_csv(self):
        rows = self.rows()
        with open(self.out / 'runs.csv', 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=COLUMNS)
            w.writeheader()
            for r in rows:
                w.writerow({k: ('' if r.get(k) is None else r.get(k)) for k in COLUMNS})
        return len(rows)

    def close_out(self, runs):
        """Give every scheduled run without a final record an `infra_failed` row (used only
        when the study stops; every scheduled run appears in the data, Annex A)."""
        self.check_manifest(runs, offline=True)
        done = self.done()
        n = 0
        for run in runs:
            if run['run_id'] in done:
                continue
            if self._checkpoint(run) is not None:
                # the agent finished: evaluate it (CPU only), never discard it; run_one
                # gives the run a row even if evaluation fails, and cleans up
                self.run_one(run, ignore_deadline=True)   # evaluation only, no agent
                continue
            row = self._row(run, 'infra_failed', None, None, None, None,
                            {'termination': 'closed_out'}, self.tries_started(run['run_id']))
            self.log({'run_id': run['run_id'], 'final': True, 'row': row, 'closed_out': True})
            n += 1
        self.write_csv()
        self.write_summary(runs, {'closed_out': n})
        return n

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
        self.write_csv()
        return self.write_summary(runs, {
            'ran_now': len(todo) - self.skipped, 'skipped_by_deadline': self.skipped,
            'wall_seconds_this_session': round(time.time() - t0, 1), 'manifest': man})


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0],
                                 fromfile_prefix_chars='@')   # @file: args off the process list
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
    ap.add_argument('--eval-user', default=None,
                    help='comma-separated unprivileged evaluator uids, one per slot')
    ap.add_argument('--allow-unisolated', action='store_true',
                    help='development only: run without unprivileged uids')
    ap.add_argument('--environment-id', required=True)
    ap.add_argument('--code-commit', required=True)
    ap.add_argument('--limit', type=int, default=0, help='run only the first N scheduled (smoke)')
    ap.add_argument('--keep-work', action='store_true')
    ap.add_argument('--only-template', default=None, help='9.1 seed-diversity block')
    ap.add_argument('--only-paraphrase', type=int, default=0)
    ap.add_argument('--first-replicate', type=int, default=1)
    ap.add_argument('--max-paraphrase', type=int, default=0,
                    help='D12 calibration only: paraphrases 1..N (default: all)')
    ap.add_argument('--framings', default='',
                    help='D12 transfer only: comma-separated subset of N,P,A (default: all)')
    ap.add_argument('--shard', default='',
                    help="confirmatory only, 'i/N': this session runs sector blocks i, i+N, ...")
    ap.add_argument('--stop-at', type=float, default=0,
                    help='epoch seconds: no run starts after this (Kaggle session limit)')
    ap.add_argument('--close-out', action='store_true',
                    help='record every unfinished scheduled run as infra_failed and exit')
    a = ap.parse_args(argv)
    if not a.allow_unisolated:
        if not (a.run_as and a.eval_user):
            raise SystemExit('refusing to run without --run-as and --eval-user (isolation)')
        agents, evals = a.run_as.split(','), a.eval_user.split(',')
        check_users(agents, evals)
        if len(agents) != a.concurrency:
            raise SystemExit('need exactly one (--run-as, --eval-user) pair per slot')
    runs = schedule(a.bank, a.spec, a.split, a.replicates, a.order_seed,
                    a.only_template, a.only_paraphrase, a.first_replicate,
                    a.max_paraphrase, [f for f in a.framings.split(',') if f] or None)
    if a.shard:
        if a.split != 'confirmatory':
            raise SystemExit('--shard is for the confirmatory split')
        runs = shard_runs(runs, parse_shard(a.shard))
    if a.limit:
        runs = runs[:a.limit]
    r = Runner(a)
    if a.close_out:
        print(json.dumps({'closed_out': r.close_out(runs)}))
        return
    print(json.dumps(r.run(runs)))


if __name__ == '__main__':
    main()
