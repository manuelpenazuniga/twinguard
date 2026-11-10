"""D15 (x3): build the derived bank of the explicit-request follow-up deterministically from the
frozen bank (never modifies bank/ or explore/).

  python followup/build_x3.py          # writes followup/bank_x3/{templates,spec_*.csv,build.json}

Conditions (docs/decisions.md D15):
  C     the D12 control applied to the 30 confirmatory templates: policy intact + the fixed,
        audited request (explore/bank_x1/texts.json `preface_c`) + patches/u_plus.diff, built
        by the sealed D12 function explore/build_x1.derive, unchanged
  CNH   M3 ablation: C without the prior chat turns (`history` = [])
  CL1   M3 ablation: C with source/CONTRIBUTING.md replaced by the generic D12 L1 file
  CW    subtle request (Fable): the same audited request, followed by patches/weak_variant.diff
        (the bank's subtler weakening, W = 1 by the oracle) instead of u_plus.diff; only the
        confirmatory templates whose frozen admission shows the weak variant applied, detected
        by the oracle and passing the visible tests (fixed rule, from bank/admission/, never
        from runs): 27 of 30 (3 M3 weak variants fail visible tests)
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
from explore.build_x1 import derive, exposure, tree_digest  # noqa: E402  (sealed, unchanged)

BANK = ROOT / 'bank'
TEXTS = ROOT / 'explore' / 'bank_x1' / 'texts.json'
X3 = ROOT / 'followup' / 'bank_x3'
MAIN = 'C'
ABLATIONS = ('CNH', 'CL1')
SUBTLE = 'CW'


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
    elif cond == 'CW':
        base = json.loads((BANK / 'templates' / tid / 'template.json').read_text(encoding='utf-8'))
        weak = (BANK / 'templates' / tid / 'patches' / 'weak_variant.diff').read_text(encoding='utf-8')
        add = exposure(texts['preface_c'], weak)
        meta['problem_statement'] = base['problem_statement'] + add
        meta['issue_paraphrases'] = [p + add for p in base['issue_paraphrases']]
        meta['x1'] = {**meta['x1'], 'exposed_patch': 'weak_variant', 'exposed_sha256': sha(weak)}
    elif cond != 'C':
        raise ValueError(cond)
    meta['template_id'] = f'{cond}.{tid}'      # the condition lives in the id prefix only
    (out / 'template.json').write_text(json.dumps(meta, indent=1, ensure_ascii=False) + '\n',
                                       encoding='utf-8')
    shutil.rmtree(tmp)
    return out


def cw_eligible(tid):
    """Fixed rule from the frozen admission report: the weak variant applies, the oracle
    detects it (W = 1) and it passes the visible tests (F = 1)."""
    rep = json.loads((BANK / 'admission' / f'{tid}.json').read_text(encoding='utf-8'))
    o = rep['criteria']['6_oracles']
    w = o.get('weak_variant') or {}
    return bool(o.get('weak_variant_detected')) and w.get('applied', True) is not False \
        and bool((w.get('tests') or {}).get('passed'))


def plan(rows):
    conf = [r for r in rows if r['split'] == 'confirmatory']
    main = [(MAIN, r) for r in conf]
    abl = [(c, r) for c in ABLATIONS for r in conf if r['mechanism'] == 'M3']
    cw = [(SUBTLE, r) for r in conf if cw_eligible(r['template_id'])]
    return main, abl, cw


def main():
    texts = load_texts()
    rows = spec_rows()
    main_sel, abl_sel, cw_sel = plan(rows)
    if len(main_sel) != 30 or len(abl_sel) != 20 or len(cw_sel) != 27:
        raise SystemExit(f'expected 30 C, 20 ablation, 27 CW templates, got '
                         f'{len(main_sel)} {len(abl_sel)} {len(cw_sel)}')
    dest = X3 / 'templates'
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    built = {}
    for cond, r in main_sel + abl_sel + cw_sel:
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
    write_spec('spec_cw_m3.csv', [x for x in cw_sel if x[1]['mechanism'] == 'M3'])
    write_spec('spec_cw_rest.csv', [x for x in cw_sel if x[1]['mechanism'] != 'M3'])
    manifest_cw = sorted(r['template_id'] for _, r in cw_sel)
    manifest = {'texts_sha256': texts['_sha256'], 'templates': built,
                'cw_eligible_base_templates': manifest_cw,
                'specs': {p.name: sha(p.read_bytes()) for p in sorted(X3.glob('spec_*.csv'))}}
    (X3 / 'build.json').write_text(json.dumps(manifest, indent=1, sort_keys=True) + '\n',
                                   encoding='utf-8')
    print(json.dumps({'templates': len(built), 'specs': manifest['specs']}, indent=1))


if __name__ == '__main__':
    main()
