"""D15 (x3): build the derived bank of the explicit-request follow-up deterministically from the
frozen bank (never modifies bank/ or explore/).

  python followup/build_x3.py          # writes followup/bank_x3/{templates,spec_*.csv,build.json}

Conditions (docs/decisions.md D15):
  C     the D12 control applied to the 30 confirmatory templates: policy intact + the fixed,
        audited request (explore/bank_x1/texts.json `preface_c`) + patches/u_plus.diff, built
        by the sealed D12 function explore/build_x1.derive, unchanged
  CNH   M3 ablation: C without the prior chat turns (`history` = [])
  CL1   M3 ablation: C with source/CONTRIBUTING.md replaced by the generic D12 L1 file
The ablations are built for the 10 confirmatory M3 templates only. Everything else (code,
tests, oracles, patches, README, monitor) is copied unchanged. Template ids get the condition as
a prefix, so run seeds are new and shared between framings.
"""
import csv
import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from explore.build_x1 import derive, tree_digest  # noqa: E402  (sealed, imported unchanged)

BANK = ROOT / 'bank'
TEXTS = ROOT / 'explore' / 'bank_x1' / 'texts.json'
X3 = ROOT / 'followup' / 'bank_x3'
MAIN = 'C'
ABLATIONS = ('CNH', 'CL1')


def sha(b):
    return hashlib.sha256(b if isinstance(b, bytes) else b.encode()).hexdigest()


def load_texts():
    texts = json.loads(TEXTS.read_text(encoding='utf-8'))
    if texts.get('problems') or not texts.get('preface_ok'):
        raise SystemExit(f'texts.json not usable: {texts.get("problems")}')
    texts['_sha256'] = sha(TEXTS.read_bytes())
    return texts


def spec_rows():
    seen, rows = set(), []
    for r in csv.DictReader(open(BANK / 'spec_matrix.csv', encoding='utf-8')):
        if r['template_id'] not in seen:      # spec_matrix.csv repeats one row; keep the first
            seen.add(r['template_id'])
            rows.append(r)
    return rows


def derive_x3(tid, cond, texts, dest):
    """C through the sealed D12 derive; CNH / CL1 = that C plus one change."""
    tmp = dest / '_tmp'
    tmp.mkdir(parents=True, exist_ok=True)
    c = derive(tid, 'C', texts, tmp)
    out = dest / f'{cond}.{tid}'
    if out.exists():
        shutil.rmtree(out)
    shutil.move(str(c), str(out))
    meta = json.loads((out / 'template.json').read_text(encoding='utf-8'))
    if cond == 'CNH':
        meta['history'] = []
    elif cond == 'CL1':
        (out / 'source' / 'CONTRIBUTING.md').write_text(texts['contributing_md'], encoding='utf-8')
    elif cond != 'C':
        raise ValueError(cond)
    meta['template_id'] = f'{cond}.{tid}'      # the condition lives in the id prefix only
    (out / 'template.json').write_text(json.dumps(meta, indent=1, ensure_ascii=False) + '\n',
                                       encoding='utf-8')
    shutil.rmtree(tmp)
    return out


def plan(rows):
    conf = [r for r in rows if r['split'] == 'confirmatory']
    main = [(MAIN, r) for r in conf]
    abl = [(c, r) for c in ABLATIONS for r in conf if r['mechanism'] == 'M3']
    return main, abl


def main():
    texts = load_texts()
    rows = spec_rows()
    main_sel, abl_sel = plan(rows)
    if len(main_sel) != 30 or len(abl_sel) != 20:
        raise SystemExit(f'expected 30 C and 20 ablation templates, got {len(main_sel)} {len(abl_sel)}')
    dest = X3 / 'templates'
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    built = {}
    for cond, r in main_sel + abl_sel:
        out = derive_x3(r['template_id'], cond, texts, dest)
        built[out.name] = tree_digest(out)
    fields = list(rows[0].keys())

    def write_spec(name, sel):
        with open(X3 / name, 'w', newline='', encoding='utf-8') as fh:
            w = csv.DictWriter(fh, fieldnames=fields, lineterminator='\n')
            w.writeheader()
            for cond, r in sel:
                w.writerow({**r, 'template_id': f"{cond}.{r['template_id']}"})
    write_spec('spec_main.csv', main_sel)
    write_spec('spec_m3.csv', abl_sel)
    manifest = {'texts_sha256': texts['_sha256'], 'templates': built,
                'specs': {p.name: sha(p.read_bytes()) for p in sorted(X3.glob('spec_*.csv'))}}
    (X3 / 'build.json').write_text(json.dumps(manifest, indent=1, sort_keys=True) + '\n',
                                   encoding='utf-8')
    print(json.dumps({'templates': len(built), 'specs': manifest['specs']}, indent=1))


if __name__ == '__main__':
    main()
