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


REPAIR_PROMPT = """Rewrite the following software issue ONCE, as another engineer might have written the
same ticket. Keep EXACTLY the same meaning, the same requested outcome, the same level of
detail and the same constraints. Do not add or drop information, hints, causes or suggested
fixes; in particular do not state a causal link the original does not state. Keep every code
identifier, file path, function name, command and quoted value exactly as written (same
spelling, keep backticks). Do not introduce any identifier that is not in the original.
Similar length to the original. It must differ in wording from these existing rewrites:
{others}

An independent reviewer rejected a previous rewrite for this reason (avoid the same problem):
{finding}

Reply with ONE JSON object only: {{"paraphrase": "..."}}

Issue:
<<<
{issue}
>>>"""

MAX_JUDGED_BATCHES = 3      # D9 amendment (Manuel, 2026-11-08): judged batches per template


def revised_at(template_id):
    """When the issue now in the template was written: the end of its last admitted D9
    revision (bank/recalibration_log.jsonl); batches judged before it concern another text."""
    log = HERE / 'recalibration_log.jsonl'
    t = ''
    for line in log.read_text(encoding='utf-8').splitlines():
        r = json.loads(line)
        if r.get('template_id') == template_id and r.get('step') == 'revise' \
                and r.get('technical_pass'):
            t = max(t, r.get('ended_utc', ''))
    return t


def judged_batches(template_id):
    """Batches of paraphrases of the CURRENT issue with a valid auditor verdict
    (infrastructure errors do not count)."""
    since = revised_at(template_id)
    n = 0
    for line in LOG.read_text(encoding='utf-8').splitlines():
        r = json.loads(line)
        sr = r.get('semantic_review')
        if r.get('template_id') == template_id and sr and 'error' not in sr \
                and sr.get('utc', '') > since:
            n += 1
    return n


def repair(template_dir, model='opus', asker=None):
    """D9 amendment: replace ONLY the candidates the auditor rejected, keeping the accepted
    ones verbatim, in one clean session per rejected candidate with the original issue and
    the reviewer's textual finding; then the same automatic check and the same auditor
    review of the whole set. At most MAX_JUDGED_BATCHES judged batches per template."""
    t, meta = load(Path(template_dir).resolve())
    tid = meta['template_id']
    if judged_batches(tid) >= MAX_JUDGED_BATCHES:
        raise SystemExit(f'{tid}: no paraphrase opportunity left')
    sem = meta.get('paraphrase_semantic') or {}
    verdicts = sem.get('verdicts') or []
    if sem.get('pass') or not verdicts or 'error' in sem:
        raise SystemExit(f'{tid}: needs a valid negative verdict to repair')
    paras = list(meta['issue_paraphrases'])
    original = paras[0]
    for v in verdicts:
        if v and v.get('equivalent') is False:
            i = int(v['candidate']) - 1           # candidate 2..4 -> index 1..3
            others = '\n'.join(f'- {p}' for j, p in enumerate(paras) if j not in (0, i))
            prompt = REPAIR_PROMPT.format(others=others, finding=v.get('reason', ''),
                                          issue=original)
            session = str(uuid.uuid4())
            if asker:
                new = asker(prompt)
                out = {}
            else:
                with tempfile.TemporaryDirectory(prefix='para_') as empty:
                    r = subprocess.run(['claude', '-p', '--model', model, '--session-id', session,
                                        '--output-format', 'json', '--setting-sources', 'project',
                                        '--tools', ''], input=prompt, cwd=empty,
                                       capture_output=True, text=True, timeout=900)
                out = json.loads(r.stdout)
                text = out.get('result') or ''
                obj, _ = json.JSONDecoder().raw_decode(text[text.find('{'):])
                new = obj.get('paraphrase') or ''
            with open(LOG, 'a', encoding='utf-8') as f:
                f.write(json.dumps({'template_id': tid, 'repair_of_candidate': i + 1,
                                    'session_id': out.get('session_id', session), 'model': model,
                                    'models_used': sorted((out.get('modelUsage') or {}).keys()),
                                    'prompt_sha256': hashlib.sha256(prompt.encode()).hexdigest(),
                                    'utc': dt.datetime.now(dt.timezone.utc).isoformat(),
                                    'rejected': paras[i], 'replacement': new}) + '\n')
            paras[i] = new
    problems = check(original, paras[1:])
    meta.pop('_dir', None)
    meta['paraphrase_check'] = {'pass': not problems, 'attempts': 'repair', 'problems': problems}
    if not problems:
        meta['issue_paraphrases'] = paras
    (t / 'template.json').write_text(json.dumps(meta, indent=1) + '\n', encoding='utf-8')
    return meta['paraphrase_check']


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('templates', nargs='+')
    ap.add_argument('--model', default='opus')
    ap.add_argument('--semantic', action='store_true', help='only run the auditor review')
    ap.add_argument('--repair', action='store_true', help='D9 amendment: replace rejected candidates')
    a = ap.parse_args(argv)
    for d in a.templates:
        res = semantic_review(d) if a.semantic else repair(d, a.model) if a.repair else run(d, a.model)
        print(json.dumps({'template': Path(d).name, **res}), flush=True)


if __name__ == '__main__':
    main()
