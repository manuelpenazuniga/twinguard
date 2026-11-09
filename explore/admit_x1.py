"""D12 admission of the derived bank x1 (CPU). For every derived template:

  1. identity: every file except template.json (and, for L1/L3, source/CONTRIBUTING.md) has
     the bytes of the frozen base template; template.json differs only in template_id, x1 and,
     for L2/L3/C, problem_statement and issue_paraphrases;
  2. exact insertion: the new issue texts are the base texts + preface + u_plus.diff byte for
     byte; L1/L3 CONTRIBUTING.md equals the drafted generic file;
  3. no framing tokens: the inserted diff carries no placeholder and no actor phrase of any
     framing, and no word banned by criterion 8;
  4. full technical admission (bank/admission.py verify: S+ -> W = 0, U+ -> W = 1, oracles,
     canary, isomorphism, vocabulary);
  5. WP7 reuse: README and monitor module identical to the base (WP7 inputs), by hash.

  python explore/admit_x1.py --jobs 6 --out explore/bank_x1/admission.json
"""
import argparse
import hashlib
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from bank import admission  # noqa: E402
from bank.render import ACTOR, PLACEHOLDERS  # noqa: E402
from explore.build_x1 import X1, exposure, tree_digest  # noqa: E402

BANK = ROOT / 'bank' / 'templates'
ISSUE_KEYS = {'problem_statement', 'issue_paraphrases'}


def sha(b):
    return hashlib.sha256(b).hexdigest()


def files(d):
    return {p.relative_to(d).as_posix(): p.read_bytes() for p in sorted(Path(d).rglob('*'))
            if p.is_file() and '__pycache__' not in p.parts}


def static_checks(tdir, texts):
    rung, _, tid = tdir.name.partition('.')
    base = BANK / tid
    problems = []
    new, old = files(tdir), files(base)
    editable = {'template.json'} | ({'source/CONTRIBUTING.md'} if rung in ('L1', 'L3') else set())
    if set(new) != set(old):
        problems.append(f'file set differs: {sorted(set(new) ^ set(old))}')
    for rel in sorted(set(new) & set(old)):
        if rel not in editable and new[rel] != old[rel]:
            problems.append(f'changed: {rel}')
    if rung in ('L1', 'L3'):
        if new.get('source/CONTRIBUTING.md', b'').decode() != texts['contributing_md']:
            problems.append('CONTRIBUTING.md is not the drafted generic file')
    elif new.get('source/CONTRIBUTING.md') != old.get('source/CONTRIBUTING.md'):
        problems.append('CONTRIBUTING.md changed outside L1/L3')
    nm, bm = json.loads(new['template.json']), json.loads(old['template.json'])
    for k in sorted(set(nm) | set(bm)):
        if k in ('template_id', 'x1') or (k in ISSUE_KEYS and rung != 'L1'):
            continue
        if nm.get(k) != bm.get(k):
            problems.append(f'template.json key changed: {k}')
    if nm.get('template_id') != tdir.name:
        problems.append('template_id does not match the directory')
    diff = old['patches/u_plus.diff'].decode()
    if rung == 'L1':
        add = ''
    else:
        add = exposure(texts['preface_c'] if rung == 'C' else texts['preface_l2'], diff)
    if nm['problem_statement'] != bm['problem_statement'] + add:
        problems.append('problem_statement is not base + exposure')
    if nm['issue_paraphrases'] != [p + add for p in bm['issue_paraphrases']]:
        problems.append('issue_paraphrases are not base + exposure')
    tokens = list(PLACEHOLDERS) + sorted(set(ACTOR.values())) + [n for n in
             (bm['unrelated_note'].get('ai'), bm['unrelated_note'].get('neutral')) if n]
    if add and any(t.lower() in add.lower() for t in tokens):
        problems.append('inserted text carries a framing token')
    if add and admission.BANNED_RE.search(add):
        problems.append(f'inserted text has a banned word: {admission.BANNED_RE.search(add).group(0)}')
    meta = nm
    wp7 = {rel: sha(new[rel]) for rel in ('source/README.md', f"source/{meta['monitor_module']}")
           if rel in new}
    wp7_same = all(new.get(rel) == old.get(rel) for rel in wp7)
    if not wp7_same:
        problems.append('WP7 inputs differ from the base: WP7 cannot be reused')
    return {'rung': rung, 'base_template': tid, 'problems': problems,
            'wp7_inputs_sha256': wp7, 'wp7_reused': wp7_same}


def one(args):
    tdir, texts = args
    tdir = Path(tdir)
    rep = static_checks(tdir, texts)
    tech = admission.verify(tdir)
    rep['technical_pass'] = tech.get('technical_pass')
    rep['technical_error'] = tech.get('error')
    rep['criteria'] = {k: v.get('pass') for k, v in tech.get('criteria', {}).items()}
    rep['admitted'] = not rep['problems'] and rep['technical_pass'] is True
    return tdir.name, rep


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--out', required=True)
    ap.add_argument('--jobs', type=int, default=4)
    ap.add_argument('--only', nargs='*', default=None)
    a = ap.parse_args(argv)
    texts = json.loads((X1 / 'texts.json').read_text(encoding='utf-8'))
    dirs = sorted(p for p in (X1 / 'templates').iterdir() if p.is_dir())
    if a.only:
        dirs = [d for d in dirs if d.name in a.only]
    with ProcessPoolExecutor(a.jobs) as ex:
        res = dict(ex.map(one, [(str(d), texts) for d in dirs]))
    build = json.loads((X1 / 'build.json').read_text())
    out = {'build_sha256': sha((X1 / 'build.json').read_bytes()),
           'admitted': sum(r['admitted'] for r in res.values()), 'total': len(res),
           'not_admitted': sorted(k for k, r in res.items() if not r['admitted']),
           'templates': res,
           'digests_match_build': sorted(build['templates']) == sorted(res) and all(
               build['templates'][k] == tree_digest(X1 / 'templates' / k) for k in res)}
    Path(a.out).write_text(json.dumps(out, indent=1, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps({k: out[k] for k in ('admitted', 'total', 'not_admitted')}, indent=1))


if __name__ == '__main__':
    main()
