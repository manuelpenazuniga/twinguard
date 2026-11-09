"""Bank facts for the writeup (WP14), each with its source file: composition, admission,
the D9 recalibration (attempts, retries, adjudications), paraphrases, WP6 and WP7.
No subject (Gemma) data are read.

  python resource/bank_facts.py --out results/bank_facts.md
"""
import argparse
import collections
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BANK = ROOT / 'bank'


def jsonl(p):
    return [json.loads(l) for l in Path(p).read_text(encoding='utf-8').splitlines() if l.strip()]


def facts():
    F = []
    add = lambda name, value, source: F.append((name, value, source))
    spec = list(csv.DictReader(open(BANK / 'spec_matrix.csv', encoding='utf-8')))
    split = collections.Counter(r['split'] for r in spec)
    add('templates (confirmatory / pilot)', f"{split['confirmatory']} / {split['pilot']}",
        'bank/spec_matrix.csv')
    conf = [r for r in spec if r['split'] == 'confirmatory']
    add('sectors (confirmatory)', len({r['family'] for r in conf}), 'bank/spec_matrix.csv')
    add('confirmatory per mechanism', dict(sorted(collections.Counter(r['mechanism'] for r in conf).items())),
        'bank/spec_matrix.csv')
    adm = {p.stem: json.loads(p.read_text()) for p in sorted((BANK / 'admission').glob('*.json'))}
    add('technical admission pass (WP5)', f"{sum(1 for v in adm.values() if v.get('technical_pass'))}/{len(adm)}",
        'bank/admission/*.json')
    gen = jsonl(BANK / 'generation_log.jsonl')
    # rows != sessions (Sol review): a session can be logged again as an annotation, and some
    # rows are notes without a session id (killed attempts, infrastructure-failure notes)
    sess = {}
    for g in gen:
        if g.get('session_id'):
            sess.setdefault(g['session_id'], []).append(g)
    with_id = sum(len(v) for v in sess.values())
    add('generation log rows', f"{len(gen)} = {with_id} session records "
        f"({with_id - len(sess)} repeat a session as an annotation) + "
        f"{len(gen) - with_id} notes without a session id", 'bank/generation_log.jsonl')
    first = {k: v[0] for k, v in sess.items()}
    limit = sorted(k for k, g in first.items()
                   if g.get('exit_code') not in (0, None) and 'limit' in str(g.get('final', '')).lower())
    done = sorted(k for k, g in first.items() if g.get('exit_code') == 0)
    add('distinct generator sessions (clean Claude sessions, WP4)',
        f"{len(sess)}: {len(done)} completed (exit 0), {len(limit)} ended by the generator "
        f"account usage limit (infrastructure), {len(sess) - len(done) - len(limit)} other",
        'bank/generation_log.jsonl')
    add('generator models', sorted({m for g in first.values() for m in (g.get('models_used') or [])}),
        'bank/generation_log.jsonl')
    rec = jsonl(BANK / 'recalibration_log.jsonl')
    rev = [r for r in rec if r.get('step') == 'revise']
    pol = [r for r in rec if r.get('step') == 'policy']
    add('D9 revision sessions (all, incl. trial and voided)', len(rev), 'bank/recalibration_log.jsonl')
    add('D9 policy checks with a verdict / infrastructure errors',
        f"{sum(1 for p in pol if 'error' not in p['result'])} / {sum(1 for p in pol if 'error' in p['result'])}",
        'bank/recalibration_log.jsonl')
    metas = {p.parent.name: json.loads(p.read_text()) for p in sorted((BANK / 'templates').glob('*/template.json'))}
    final = {}
    for r in rec:                                   # the revision now in the bank: last admitted
        if r.get('step') == 'revise' and r.get('technical_pass'):
            final[r['template_id']] = r
        elif r.get('step') == 'restore':
            final[r['template_id']] = {**r, 'retry_with_feedback': False}
    retried = sorted(t for t, r in final.items() if r.get('retry_with_feedback'))
    add('templates admitted after one retry with findings', retried, 'bank/recalibration_log.jsonl')
    adjud = sorted(t for t, m in metas.items()
                   if ((m.get('recalibration') or {}).get('policy_preservation') or {}).get('adjudication'))
    add('templates admitted through a §6.4 adjudication', adjud, 'bank/templates/*/template.json')
    add('WP7 inputs unchanged (WP7 reused)',
        f"{sum(1 for m in metas.values() if ((m.get('recalibration') or {}).get('wp7_inputs') or {}).get('reuse'))}/{len(metas)}",
        'bank/templates/*/template.json')
    para = jsonl(BANK / 'paraphrase_log.jsonl')
    add('paraphrase candidates repaired (D9 amendment)', sum(1 for p in para if 'repair_of_candidate' in p),
        'bank/paraphrase_log.jsonl')
    add('paraphrase sets passing (automatic + auditor)',
        f"{sum(1 for m in metas.values() if (m.get('paraphrase_check') or {}).get('pass') and (m.get('paraphrase_semantic') or {}).get('pass'))}/{len(metas)}",
        'bank/templates/*/template.json')
    last = {}
    for r in jsonl(BANK / 'audits' / 'semantic_audit_level2.jsonl'):
        if 'summary' in r:
            last[r['template_id']] = r['summary'].get('verdict')
    add('WP6 last verdict', dict(collections.Counter(last.values())),
        'bank/audits/semantic_audit_level2.jsonl')
    return F


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--out', required=True)
    a = ap.parse_args(argv)
    F = facts()
    lines = ['# TwinGuard bank facts (generated; every value with its source)', '',
             '| Fact | Value | Source |', '|---|---|---|']
    lines += [f'| {n} | `{json.dumps(v, ensure_ascii=False)}` | `{s}` |' for n, v, s in F]
    Path(a.out).write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('\n'.join(lines))


if __name__ == '__main__':
    main()
