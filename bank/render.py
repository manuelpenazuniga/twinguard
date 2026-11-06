"""Template format and deterministic N/P/A renderer (protocol 5.1, 5.3, 6.3).

A template is generated ONCE with placeholders; the three framings are rendered from
it, so isomorphism holds by construction and is then verified (bank/admission.py).

bank/templates/<template_id>/
    template.json      template_id, mechanism, repo, problem_statement, history (M3),
                       unrelated_note {neutral, ai}, protected [patterns], monitors
                       [patterns], generator {model, session_id, prompt_sha256}
    source/            the repository; {{ACTOR}} and {{UNRELATED_NOTE}} may appear ONLY
                       in docstrings, comments and Markdown files
    patches/           s_plus.diff, u_plus.diff, alt_safe.diff (git diffs against the
                       rendered N workspace; code only, never docstrings or tests)
    oracle/oracle.py   behavioural oracle with external spies; NEVER copied into the
                       workspace. `python oracle.py <workspace>` prints one JSON line:
                       {"crash": bool, "checks": {"<invariant>": bool, ...}}
                       where True means the invariant HOLDS (canary included).

Framings: only the actor phrase changes between N and A; P equals N plus an AI mention
in an unrelated module ({{UNRELATED_NOTE}}). Same article ("an") in both phrases.
"""
import json
import shutil
from pathlib import Path

FRAMINGS = ('N', 'P', 'A')
ACTOR = {'N': 'batch service', 'P': 'batch service', 'A': 'AI agent'}
PLACEHOLDERS = ('{{ACTOR}}', '{{UNRELATED_NOTE}}')
TEXT_SUFFIXES = {'.py', '.md', '.txt', '.toml', '.cfg', '.ini', '.json', '.yaml', '.yml'}


def load(template_dir):
    t = Path(template_dir)
    meta = json.loads((t / 'template.json').read_text(encoding='utf-8'))
    return t, meta


def values(meta, framing):
    note = meta['unrelated_note']['ai' if framing == 'P' else 'neutral']
    return {'{{ACTOR}}': ACTOR[framing], '{{UNRELATED_NOTE}}': note}


def render_text(text, meta, framing):
    for k, v in values(meta, framing).items():
        text = text.replace(k, v)
    return text


def render(template_dir, framing, dest):
    """Copy source/ to dest with placeholders substituted. Returns dest."""
    if framing not in FRAMINGS:
        raise ValueError(f'unknown framing {framing!r}')
    t, meta = load(template_dir)
    src = t / 'source'
    dest = Path(dest)
    if dest.exists():
        shutil.rmtree(dest)
    for p in sorted(src.rglob('*')):
        rel = p.relative_to(src)
        out = dest / rel
        if p.is_dir():
            out.mkdir(parents=True, exist_ok=True)
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        if p.suffix in TEXT_SUFFIXES or p.name.startswith('README'):
            out.write_text(render_text(p.read_text(encoding='utf-8'), meta, framing),
                           encoding='utf-8')
        else:
            shutil.copyfile(p, out)
    return dest


def task_for(meta):
    """Task given to the agent: identical across framings by construction."""
    return {'repo': meta['repo'], 'problem_statement': meta['problem_statement'],
            'history': meta.get('history', []), 'hints': meta.get('hints', '')}
