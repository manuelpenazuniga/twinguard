"""WP4: generate ONE template per clean Claude session (protocol 6.3).

Each row of bank/spec_matrix.csv is built by a fresh headless `claude -p` session that
runs in an isolated, empty kit directory (outside this repo: it cannot see the protocol,
the analysis or the other templates). The kit holds only the renderer, the verifier and
the graph module it needs. Permissions are restricted: edits only inside the kit
(acceptEdits) and an allowlist of Bash commands (python, git, basic file inspection);
anything else is denied in headless mode.

The session id, exact model, prompt sha256 and timings are appended to
bank/generation_log.jsonl; the package is copied to bank/templates/<id>/ and verified
again here, writing bank/admission/<id>.json.

Usage: python bank/generate.py <template_id> [...] --kit-root DIR [--model opus]
"""
import argparse
import csv
import datetime as dt
import hashlib
import json
import shutil
import subprocess
import sys
import tomllib
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from bank import admission  # noqa: E402
from bank.render import SENTENCES  # noqa: E402

PROMPT = HERE / 'generator_prompt.md'
LOG = HERE / 'generation_log.jsonl'
KIT_FILES = {'bank/__init__.py': HERE / '__init__.py', 'bank/render.py': HERE / 'render.py',
             'bank/admission.py': HERE / 'admission.py',
             'twinguard/twinguard_graph.py': ROOT / 'twinguard' / 'twinguard_graph.py'}
BASH_ALLOW = ['python', 'python3', sys.executable, 'git', 'ls', 'cat', 'head', 'tail', 'wc',
              'diff', 'mkdir', 'cp', 'find', 'grep']


def rows():
    with open(HERE / 'spec_matrix.csv', encoding='utf-8') as f:
        return {r['template_id']: r for r in csv.DictReader(f)}


def contracts():
    data = tomllib.loads((HERE / 'sectors.toml').read_text(encoding='utf-8'))
    return {m: v['contract'].strip() for m, v in data['mechanisms'].items()}


def build_prompt(row, python):
    text = PROMPT.read_text(encoding='utf-8')
    fields = {'TEMPLATE_ID': row['template_id'], 'MECHANISM': row['mechanism'],
              'FAMILY': row['family'], 'SUBDOMAIN': row['subdomain'],
              'SCENARIO_SEED': row['scenario_seed'], 'STYLE': row['style'],
              'ACTOR_ID': row['actor_identifier'], 'MONITOR_ID': row['monitor_identifier'],
              'CONTRACT': contracts()[row['mechanism']],
              'CRITICALITY_SENTENCE': SENTENCES[row['mechanism']], 'PYTHON': python}
    for k, v in fields.items():
        text = text.replace('{{' + k + '}}', v)
    return text


def make_kit(kit):
    if kit.exists():
        shutil.rmtree(kit)
    for rel, src in KIT_FILES.items():
        (kit / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, kit / rel)
    (kit / 'out').mkdir()


def claude_cmd(model, session):
    tools = ['Read', 'Write', 'Edit', 'Glob', 'Grep'] + [f'Bash({c}:*)' for c in BASH_ALLOW]
    return ['claude', '-p', '--model', model, '--session-id', session,
            '--output-format', 'json', '--setting-sources', 'project',
            '--permission-mode', 'acceptEdits', '--allowedTools', *tools]


def generate(template_id, model, kit_root, timeout):
    row = rows()[template_id]
    prompt = build_prompt(row, sys.executable)
    sha = hashlib.sha256(prompt.encode()).hexdigest()
    kit = Path(kit_root).resolve() / template_id
    if ROOT in kit.parents:
        raise SystemExit('the kit must live outside the repository')
    make_kit(kit)
    session = str(uuid.uuid4())
    started = dt.datetime.now(dt.timezone.utc).isoformat()
    try:
        r = subprocess.run(claude_cmd(model, session), input=prompt, cwd=kit,
                           capture_output=True, text=True, timeout=timeout)
        raw, code = r.stdout, r.returncode
    except subprocess.TimeoutExpired as e:
        raw = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or '')
        code = -1
    try:
        out = json.loads(raw)
    except json.JSONDecodeError:
        out = {'unparsed': raw[-2000:]}
    (kit / 'session_output.json').write_text(json.dumps(out, indent=1), encoding='utf-8')
    entry = {'template_id': template_id, 'session_id': out.get('session_id', session),
             'requested_model': model,
             'models_used': sorted((out.get('modelUsage') or {}).keys()),
             'prompt_sha256': sha,
             'prompt_file_sha256': hashlib.sha256(PROMPT.read_bytes()).hexdigest(),
             'started_utc': started, 'ended_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
             'exit_code': code, 'num_turns': out.get('num_turns'),
             'cost_usd': out.get('total_cost_usd'), 'final': (out.get('result') or '')[-300:]}
    dest = HERE / 'templates' / template_id
    produced = kit / 'out' / template_id
    if (produced / 'template.json').exists():
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(produced, dest, ignore=shutil.ignore_patterns('__pycache__', '.git'))
        meta = json.loads((dest / 'template.json').read_text(encoding='utf-8'))
        meta['generator'] = {'model': entry['models_used'] or [model],
                             'session_id': entry['session_id'], 'prompt_sha256': sha}
        (dest / 'template.json').write_text(json.dumps(meta, indent=1) + '\n', encoding='utf-8')
        rep = admission.verify(dest)
        (HERE / 'admission').mkdir(exist_ok=True)
        (HERE / 'admission' / f'{template_id}.json').write_text(
            json.dumps(rep, indent=1, sort_keys=True) + '\n', encoding='utf-8')
        entry['technical_pass'] = rep['technical_pass']
        entry['failing'] = sorted(k for k, v in rep['criteria'].items() if v['pass'] is False)
    else:
        entry['technical_pass'] = False
        entry['failing'] = ['no package produced']
    with open(LOG, 'a', encoding='utf-8') as f:
        f.write(json.dumps(entry) + '\n')
    return entry


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('template_ids', nargs='+')
    ap.add_argument('--model', default='opus')
    ap.add_argument('--kit-root', required=True)
    ap.add_argument('--timeout', type=int, default=3600)
    a = ap.parse_args(argv)
    for tid in a.template_ids:
        print(json.dumps(generate(tid, a.model, a.kit_root, a.timeout)), flush=True)


if __name__ == '__main__':
    main()
