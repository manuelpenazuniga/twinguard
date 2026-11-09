"""D12: build the derived bank x1 deterministically from the frozen bank (never modifies bank/).

  python explore/build_x1.py            # writes explore/bank_x1/{templates,spec_*.csv,build.json}

Rungs (docs/decisions.md D12):
  L1  implicit policy: source/CONTRIBUTING.md replaced by the generic file of texts.json
  L2  shortcut exposure, policy intact: the problem statement and every paraphrase get the
      fixed preface followed by patches/u_plus.diff byte for byte (in a ```diff fence)
  L3  L1 + L2
  C   control (never eligible): policy intact + the fixed request + u_plus.diff; pilot only
Everything else (code, tests, oracle, patches, README, monitor, history) is copied unchanged.
Template ids get the rung as a prefix, so run seeds are new and shared between framings.
"""
import csv
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BANK = ROOT / 'bank'
X1 = ROOT / 'explore' / 'bank_x1'
RUNGS = ('L1', 'L2', 'L3', 'C')
ELIGIBLE = ('L1', 'L2', 'L3')


def sha(b):
    return hashlib.sha256(b if isinstance(b, bytes) else b.encode()).hexdigest()


def exposure(preface, diff):
    return f'\n\n{preface}\n\n```diff\n{diff}```'


def derive(tid, rung, texts, dest):
    src = BANK / 'templates' / tid
    out = dest / f'{rung}.{tid}'
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(src, out, ignore=shutil.ignore_patterns('__pycache__'))
    meta = json.loads((src / 'template.json').read_text(encoding='utf-8'))
    diff = (src / 'patches' / 'u_plus.diff').read_text(encoding='utf-8')
    if rung in ('L1', 'L3'):
        (out / 'source' / 'CONTRIBUTING.md').write_text(texts['contributing_md'], encoding='utf-8')
    if rung in ('L2', 'L3', 'C'):
        add = exposure(texts['preface_l2'] if rung != 'C' else texts['preface_c'], diff)
        meta['problem_statement'] = meta['problem_statement'] + add
        meta['issue_paraphrases'] = [p + add for p in meta['issue_paraphrases']]
    meta['template_id'] = f'{rung}.{tid}'
    meta['x1'] = {'rung': rung, 'base_template': tid,
                  'base_template_json_sha256': sha((src / 'template.json').read_bytes()),
                  'u_plus_sha256': sha(diff), 'texts_sha256': texts['_sha256']}
    (out / 'template.json').write_text(json.dumps(meta, indent=1, ensure_ascii=False) + '\n',
                                       encoding='utf-8')
    return out


def tree_digest(d):
    h = hashlib.sha256()
    for p in sorted(Path(d).rglob('*')):
        if p.is_file() and '__pycache__' not in p.parts:
            h.update(p.relative_to(d).as_posix().encode() + b'\0' + p.read_bytes() + b'\0')
    return h.hexdigest()


def main():
    tpath = X1 / 'texts.json'
    texts = json.loads(tpath.read_text(encoding='utf-8'))
    if texts.get('problems') or not texts.get('preface_ok'):
        raise SystemExit(f'texts.json not usable: {texts.get("problems")}')
    texts['_sha256'] = sha(tpath.read_bytes())
    spec = list(csv.DictReader(open(BANK / 'spec_matrix.csv', encoding='utf-8')))
    seen, rows = set(), []
    for r in spec:                       # spec_matrix.csv repeats one row; keep the first
        if r['template_id'] not in seen:
            seen.add(r['template_id'])
            rows.append(r)
    dest = X1 / 'templates'
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    built = {}
    for r in rows:
        rungs = RUNGS if r['split'] == 'pilot' else ELIGIBLE
        for rung in rungs:
            out = derive(r['template_id'], rung, texts, dest)
            built[out.name] = tree_digest(out)
    fields = list(rows[0].keys())

    def write_spec(name, sel):
        with open(X1 / name, 'w', newline='', encoding='utf-8') as fh:
            w = csv.DictWriter(fh, fieldnames=fields, lineterminator='\n')
            w.writeheader()
            for rung, r in sel:
                w.writerow({**r, 'template_id': f"{rung}.{r['template_id']}"})
    pilot = [r for r in rows if r['split'] == 'pilot']
    conf = [r for r in rows if r['split'] == 'confirmatory']
    write_spec('spec_calibration.csv', [(g, r) for g in RUNGS for r in pilot])
    for g in ELIGIBLE:
        write_spec(f'spec_transfer_{g}.csv', [(g, r) for r in conf])
    manifest = {'texts_sha256': texts['_sha256'], 'templates': built,
                'specs': {p.name: sha(p.read_bytes()) for p in sorted(X1.glob('spec_*.csv'))}}
    (X1 / 'build.json').write_text(json.dumps(manifest, indent=1, sort_keys=True) + '\n',
                                   encoding='utf-8')
    print(json.dumps({'templates': len(built), 'specs': manifest['specs']}, indent=1))


if __name__ == '__main__':
    main()
