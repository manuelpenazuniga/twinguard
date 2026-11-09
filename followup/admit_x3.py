"""D15 (x3) admission of the derived bank (CPU). For every derived template:

  C    the sealed D12 checks (explore/admit_x1.static_checks, imported unchanged): identity of
       every file but template.json, exact insertion of the audited request + u_plus.diff, no
       framing token, no banned word, WP7 inputs identical
  CNH  the C checks of its C twin, plus: template.json equals the C twin's except template_id,
       x3 and history, and history is empty
  CL1  the C checks of its C twin, plus: CONTRIBUTING.md is the generic D12 L1 file, every other
       file equals the C twin's
and, for all, full technical admission (bank/admission.py verify: S+ -> W = 0, U+ -> W = 1,
oracles, canary, isomorphism, vocabulary).

  python followup/admit_x3.py --jobs 6 --out followup/bank_x3/admission.json
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
from explore.admit_x1 import files, static_checks  # noqa: E402  (sealed, unchanged)
from explore.build_x1 import tree_digest  # noqa: E402
from followup.build_x3 import TEXTS, X3, derive_x3, load_texts  # noqa: E402


def sha(b):
    return hashlib.sha256(b).hexdigest()


def c_twin(tid, texts, work):
    """A fresh C build of the base template (the reference for the ablations)."""
    return derive_x3(tid, 'C', texts, Path(work))


def variant_checks(tdir, texts, work):
    cond, _, tid = tdir.name.partition('.')
    if cond == 'C':
        rep = static_checks(tdir, texts)
        rep['condition'] = 'C'
        return rep
    twin = c_twin(tid, texts, work)
    rep = static_checks(twin, texts)              # the C part of the variant, by construction
    rep['condition'] = cond
    new, ref = files(tdir), files(twin)
    probs = rep['problems']
    if set(new) != set(ref):
        probs.append(f'file set differs from C: {sorted(set(new) ^ set(ref))}')
    editable = {'template.json'} | ({'source/CONTRIBUTING.md'} if cond == 'CL1' else set())
    for rel in sorted(set(new) & set(ref)):
        if rel not in editable and new[rel] != ref[rel]:
            probs.append(f'changed vs C: {rel}')
    nm, cm = json.loads(new['template.json']), json.loads(ref['template.json'])
    skip = {'template_id'} | ({'history'} if cond == 'CNH' else set())
    for k in sorted(set(nm) | set(cm)):
        if k not in skip and nm.get(k) != cm.get(k):
            probs.append(f'template.json key changed vs C: {k}')
    if nm.get('template_id') != tdir.name:
        probs.append('template_id does not match the directory')
    if cond == 'CNH' and nm.get('history') != []:
        probs.append('CNH history is not empty')
    if cond == 'CL1' and new.get('source/CONTRIBUTING.md', b'').decode() != texts['contributing_md']:
        probs.append('CL1 CONTRIBUTING.md is not the generic D12 file')
    if nm.get('mechanism') != 'M3':
        probs.append('ablations are M3 only')
    return rep


def one(args):
    tdir, texts, work = args
    tdir = Path(tdir)
    rep = variant_checks(tdir, texts, Path(work) / tdir.name)
    tech = admission.verify(tdir)
    rep['technical_pass'] = tech.get('technical_pass')
    rep['technical_error'] = tech.get('error')
    rep['criteria'] = {k: v.get('pass') for k, v in tech.get('criteria', {}).items()}
    rep['admitted'] = not rep['problems'] and rep['technical_pass'] is True
    return tdir.name, rep


def main(argv=None):
    import tempfile
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--out', required=True)
    ap.add_argument('--jobs', type=int, default=4)
    ap.add_argument('--only', nargs='*', default=None)
    a = ap.parse_args(argv)
    texts = load_texts()
    dirs = sorted(p for p in (X3 / 'templates').iterdir() if p.is_dir())
    if a.only:
        dirs = [d for d in dirs if d.name in a.only]
    with tempfile.TemporaryDirectory() as work, ProcessPoolExecutor(a.jobs) as ex:
        res = dict(ex.map(one, [(str(d), texts, work) for d in dirs]))
    build = json.loads((X3 / 'build.json').read_text())
    out = {'build_sha256': sha((X3 / 'build.json').read_bytes()),
           'texts_sha256': sha(TEXTS.read_bytes()),
           'admitted': sum(r['admitted'] for r in res.values()), 'total': len(res),
           'not_admitted': sorted(k for k, r in res.items() if not r['admitted']),
           'templates': res,
           'digests_match_build': sorted(build['templates']) == sorted(res) and all(
               build['templates'][k] == tree_digest(X3 / 'templates' / k) for k in res)}
    Path(a.out).write_text(json.dumps(out, indent=1, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps({k: out[k] for k in ('admitted', 'total', 'not_admitted',
                                           'digests_match_build')}, indent=1))


if __name__ == '__main__':
    main()
