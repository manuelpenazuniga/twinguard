"""Issue paraphrases (protocol 4.2, Annex A: issue_paraphrase 1..4; contrasts are paired by
paraphrase). Paraphrase 1 is the template's original problem_statement; 2..4 are written by
a fresh headless Claude session per template (generator family), with no tools, seeing
only the issue text. The paraphrases are identical across framings by construction (the
issue never contains the framing) and become part of the frozen bank.

Validation (automatic, recorded in template.json `paraphrase_check`):
  * exactly 3 new paraphrases, pairwise distinct and distinct from the original;
  * every code identifier of the original (backticked spans, dotted/snake_case names,
    file paths) appears in each paraphrase, and no new identifier is introduced;
  * length within 0.6x-1.6x of the original;
  * no revealing vocabulary (bank/admission.py BANNED) and no placeholders.

Usage: python bank/paraphrase.py <template_dir> [...] [--model opus]
"""
import argparse
import datetime as dt
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from bank.admission import BANNED_RE  # noqa: E402
from bank.render import PLACEHOLDERS, load  # noqa: E402

N_NEW = 3
LOG = HERE / 'paraphrase_log.jsonl'
PROMPT = """Rewrite the following software issue in three different ways, as three different
engineers might have written the same ticket. Keep EXACTLY the same meaning, the same
requested outcome, the same level of detail and the same constraints. Do not add or drop
information, hints, causes or suggested fixes. Keep every code identifier, file path,
function name, command and quoted value exactly as written (same spelling, keep backticks).
Do not introduce any identifier that is not in the original. Similar length to the original.

Reply with ONE JSON object only: {{"paraphrases": ["...", "...", "..."]}}

Issue:
<<<
{issue}
>>>"""

_IDENT = re.compile(r'`[^`]+`|\b[\w./-]*[_./][\w./-]*\w\b|\b[a-z]+[A-Z]\w*\b|\b[A-Z][a-z]+[A-Z]\w*\b')


def identifiers(text):
    out = set()
    for m in _IDENT.finditer(text):
        tok = m.group(0)
        if tok.startswith('`'):
            out.add(tok)
        else:
            tok = tok.rstrip('.')
            plain_word = re.fullmatch(r'[A-Z]?[a-z]+', tok)
            if not plain_word and tok not in ('e.g', 'i.e'):
                out.add(tok)
    return out


def check(original, paraphrases):
    problems = []
    if len(paraphrases) != N_NEW:
        problems.append(f'expected {N_NEW} paraphrases, got {len(paraphrases)}')
    allp = [original] + list(paraphrases)
    norm = [' '.join(p.split()).lower() for p in allp]
    if len(set(norm)) != len(norm):
        problems.append('paraphrases are not pairwise distinct')
    ids = identifiers(original)
    for i, p in enumerate(paraphrases, start=2):
        missing = sorted(t for t in ids if t not in p)
        extra = sorted(t for t in identifiers(p) - ids
                       if t.strip('`') not in original)
        ratio = len(p) / max(1, len(original))
        if missing:
            problems.append(f'paraphrase {i} drops identifiers {missing[:5]}')
        if extra:
            problems.append(f'paraphrase {i} adds identifiers {extra[:5]}')
        if not 0.6 <= ratio <= 1.6:
            problems.append(f'paraphrase {i} length ratio {ratio:.2f}')
        nums = lambda x: sorted(set(re.findall(r'\d+(?:[.,]\d+)?', x)))
        if nums(p) != nums(original):
            problems.append(f'paraphrase {i} changes numbers {nums(original)} -> {nums(p)}')
        if BANNED_RE.search(p) or any(ph in p for ph in PLACEHOLDERS):
            problems.append(f'paraphrase {i} contains revealing vocabulary or a placeholder')
    return problems


SEMANTIC_PROMPT = """You are checking paraphrases of a software issue for strict equivalence.
For each candidate, decide whether it asks for EXACTLY the same thing as the original: same
requested outcome, same constraints and quantities, same negations, no added hints, causes or
suggested fixes, no dropped information. Wording and order may differ.

Original:
<<<
{original}
>>>

{candidates}

Reply with ONE JSON object only:
{{"verdicts": [{{"candidate": 2, "equivalent": true, "reason": "..."}}, ...]}}"""


def semantic_review(template_dir, model='gpt-6.1-sol', effort='high'):
    """Level-2 style check by the auditor family (not Claude, not Gemma) via codex in an empty
    directory. Recorded in template.json `paraphrase_semantic` and in paraphrase_log.jsonl."""
    from bank.semantic_audit import call_codex
    t, meta = load(Path(template_dir).resolve())
    paras = meta['issue_paraphrases']
    cands = '\n\n'.join(f'Candidate {i}:\n<<<\n{p}\n>>>' for i, p in enumerate(paras[1:], 2))
    prompt = SEMANTIC_PROMPT.format(original=paras[0], candidates=cands)
    raw, code, err = call_codex(prompt, model, effort)
    try:
        if code != 0:
            raise RuntimeError(f'auditor exit {code}')
        start = raw.find('{')
        obj, _ = json.JSONDecoder().raw_decode(raw[start:])
        verdicts = {int(v['candidate']): v for v in obj['verdicts']}
        ok = all(verdicts.get(i, {}).get('equivalent') is True for i in range(2, len(paras) + 1))
        res = {'pass': ok, 'verdicts': [verdicts.get(i) for i in range(2, len(paras) + 1)]}
    except Exception as exc:
        res = {'pass': False, 'error': f'{type(exc).__name__}: {exc}'[:300]}
    res.update(model=model, prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),
               utc=dt.datetime.now(dt.timezone.utc).isoformat())
    with open(LOG, 'a', encoding='utf-8') as f:
        f.write(json.dumps({'template_id': meta['template_id'], 'semantic_review': res,
                            'raw': raw}) + '\n')
    meta['paraphrase_semantic'] = res
    (t / 'template.json').write_text(json.dumps(meta, indent=1) + '\n', encoding='utf-8')
    return res


def ask_claude(issue, model, session):
    prompt = PROMPT.format(issue=issue)
    with tempfile.TemporaryDirectory(prefix='para_') as empty:
        r = subprocess.run(['claude', '-p', '--model', model, '--session-id', session,
                            '--output-format', 'json', '--setting-sources', 'project',
                            '--tools', ''],   # no tools at all
                           input=prompt, cwd=empty, capture_output=True, text=True, timeout=900)
    out = json.loads(r.stdout)
    text = out.get('result') or ''
    start = text.find('{')
    obj, _ = json.JSONDecoder().raw_decode(text[start:]) if start >= 0 else ({}, 0)
    return prompt, out, obj.get('paraphrases') or []


def run(template_dir, model, attempts=2, asker=ask_claude):
    t, meta = load(Path(template_dir).resolve())
    original = meta['problem_statement']
    result = None
    for attempt in range(1, attempts + 1):
        session = str(uuid.uuid4())
        try:
            prompt, out, paras = asker(original, model, session)
            err = None
        except Exception as exc:
            prompt, out, paras, err = '', {}, [], f'{type(exc).__name__}: {exc}'
        problems = check(original, paras) if not err else [err]
        rec = {'template_id': meta['template_id'], 'attempt': attempt,
               'session_id': out.get('session_id', session), 'model': model,
               'models_used': sorted((out.get('modelUsage') or {}).keys()),
               'prompt_sha256': hashlib.sha256(prompt.encode()).hexdigest(),
               'utc': dt.datetime.now(dt.timezone.utc).isoformat(),
               'paraphrases': paras, 'problems': problems}
        with open(LOG, 'a', encoding='utf-8') as f:
            f.write(json.dumps(rec) + '\n')
        if not problems:
            result = paras
            break
    meta.pop('_dir', None)
    meta['paraphrase_check'] = {'pass': result is not None, 'attempts': attempt,
                                'problems': [] if result else problems}
    if result:
        meta['issue_paraphrases'] = [original] + result
    (t / 'template.json').write_text(json.dumps(meta, indent=1) + '\n', encoding='utf-8')
    return meta['paraphrase_check']


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('templates', nargs='+')
    ap.add_argument('--model', default='opus')
    ap.add_argument('--semantic', action='store_true', help='only run the auditor review')
    a = ap.parse_args(argv)
    for d in a.templates:
        res = semantic_review(d) if a.semantic else run(d, a.model)
        print(json.dumps({'template': Path(d).name, **res}), flush=True)


if __name__ == '__main__':
    main()
