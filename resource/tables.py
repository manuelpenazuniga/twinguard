"""Writeup tables (WP14): every number comes from a results file and carries its source.

Reads a results directory written by runner/analyze.py (analysis_output.json,
truncation_report.json, gate_output.json) and, optionally, the witness table of
runner/secondary.py. Writes Markdown tables and a provenance list: for each cell, the file,
the JSON path and the raw value. Nothing is computed here except rounding and
percent formatting; a number without a source is never printed.

  python resource/tables.py --results results/confirmatory --freeze freeze/manifest.json \
      [--witnesses results/witnesses] --out results/tables.md
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT / 'twinguard') not in sys.path:
    sys.path.insert(0, str(ROOT / 'twinguard'))
from twinguard_analysis import coarse  # noqa: E402  (the frozen coarse decision classes)


class Src:
    def __init__(self):
        self.rows = []

    def get(self, path, data, keys):
        v = data
        for k in keys:
            v = v[k]
        self.rows.append((path.name, '.'.join(map(str, keys)), v))
        return v


def pp(x, digits=1):
    return '—' if x is None else f'{100 * x:.{digits}f}'


def ci(c):
    return '—' if not c else f'[{pp(c[0])}, {pp(c[1])}]'


def reported(decision, floor):
    """§10.6/§12: under the floor flag a decision is shown as non-informative, with the
    script's raw label kept in brackets for traceability."""
    return f'non-informative (floor) [{decision}]' if floor else decision


def keval(c):
    """K evaluable for the contrast and its HC3 df (df = K evaluable - 3), never K scheduled."""
    return f"{c['n_templates']} / {c['df']:g}"


def main_tables(res, src):
    p = res / 'analysis_output.json'
    a = json.loads(p.read_text())
    g = lambda *k: src.get(p, a, k)
    out = [f"Analysis status: **{g('analysis_status')}**; templates in the input "
           f"{g('n_templates')} (K evaluable per contrast below); rollouts scheduled "
           f"{g('n_rollouts_scheduled')}.", '',
           '| Framing | W (%) | F (%) | U (%) | M (%) |', '|---|---|---|---|---|']
    for f in ('N', 'P', 'A'):
        out.append(f'| {f} | ' + ' | '.join(pp(g('rates_template_weighted', f, m))
                                          for m in ('W', 'F', 'U', 'M')) + ' |')
    out += ['', '| Contrast | Estimate (pp) | 95% CI (HC3) | 90% CI | p | K evaluable / df | Decision |',
            '|---|---|---|---|---|---|---|']
    floor = bool(g('FLAGS', 'floor_or_ceiling'))
    for key, label in (('H1_PRIMARY_W_A_minus_N', 'H1: W, A − N'),
                       ('H2_SPECIFICITY_W_A_minus_P', 'H2: W, A − P'),
                       ('DIAGNOSTIC_W_P_minus_N', 'Diagnostic: W, P − N')):
        h95 = g(key, 'HC3_95')
        pv = '—' if h95['p_two_sided'] is None else f"{h95['p_two_sided']:.3f}"
        out.append(f"| {label} | {pp(h95['estimate'])} | {ci(h95['ci'])} | "
                   f"{ci(g(key, 'HC3_90', 'ci'))} | {pv} | {keval(h95)} | "
                   f"{reported(a[key].get('decision', '—'), floor)} |")
    if floor:
        out += ['', '**Floor (§10.6, §12):** the floor_or_ceiling flag is set; every decision above is '
                'reported as non-informative (floor). At a floor only increases of W are detectable; '
                '"equivalent" must not be written.']
    out += ['', f"Flags: {json.dumps(g('FLAGS'))}", '']
    hs = 'EXPLORATORY_heterogeneity_and_stability'
    rng = g(hs, 'leave_one_family_out_range')
    out += [f"Leave-one-family-out (H1, exploratory): range "
            f"{'—' if rng is None else f'[{pp(rng[0])}, {pp(rng[1])}]'} pp over "
            f"{g(hs, 'n_families')} sectors; same coarse class as the primary in "
            f"{g(hs, 'leave_one_family_out_same_class')}; not estimable "
            f"{g(hs, 'leave_one_family_out_not_estimable')}.", '']
    out += ['| Mechanism | ΔW A − N (pp, exploratory) |', '|---|---|']
    for m, v in sorted(g('EXPLORATORY_by_mechanism_dAN').items()):
        out.append(f'| {m} | {pp(v)} |')
    return out


def sensitivity_table(res, src, fz):
    """D9 reporting rule for the frozen sensitivity, driven by the FREEZE (not by whatever the
    results directory happens to hold): if one is frozen, the section is always printed. It is
    "Not available" when the seal, the record or the output is missing or failed; it is
    NON-INFORMATIVE when an excluded sector's block is not complete OR its state is unknown
    (no truncation report, or no entry for that sector). Otherwise each contrast is shown with
    its coarse class against the primary, the primary's leave-one-family-out entry for the
    excluded sector (with an equality check) and the LOFO range."""
    spec = (fz.get('design') or {}).get('sensitivity')
    ph = res / 'analysis_hashes.json'
    h = json.loads(ph.read_text()) if ph.exists() else None
    head = ['', '### Prespecified sensitivity (D9; EXPLORATORY; next to the primary, never instead of it)', '']
    if not spec:
        if h is not None and h.get('sensitivity') is not None:
            return head + ['**Inconsistent:** a sensitivity is recorded but none is frozen; it is not '
                           'reported.']
        return []
    if h is None:
        return head + ['**Not available.** No analysis_hashes.json (no sealed analysis); the frozen '
                       'sensitivity is reported as missing.']
    rec = src.get(ph, h, ('sensitivity',))
    p = res / 'analysis_sensitivity.json'
    if not isinstance(rec, dict) or rec.get('rc') != 0 or not p.exists() \
            or sorted(rec.get('excluded_families') or []) != sorted(spec['exclude_families']):
        return head + [f"**Not available.** Recorded state: `{json.dumps(rec)}`. The frozen "
                       f"sensitivity is reported as missing; no decision is drawn from it."]
    fams = sorted(spec['exclude_families'])
    pt = res / 'truncation_report.json'
    state = {f: 'unknown (no truncation report)' for f in fams}
    if pt.exists():
        t = json.loads(pt.read_text())
        state = {f: 'unknown (no entry in the truncation report)' for f in fams}
        for i, b in enumerate(t.get('blocks', [])):
            if b.get('family') in fams:
                state[b['family']] = src.get(pt, t, ('blocks', i, 'state'))
    incomplete = [f'{f}: {st}' for f, st in state.items() if st != 'complete']
    a = json.loads(p.read_text())
    g = lambda *k: src.get(p, a, k)
    pa = res / 'analysis_output.json'
    prim = json.loads(pa.read_text())
    gp = lambda *k: src.get(pa, prim, k)
    floor = bool(g('FLAGS', 'floor_or_ceiling'))
    out = head + [f"Without sector(s) {', '.join(fams)} (templates in the input {g('n_templates')}; "
                  f"status {g('analysis_status')}).", '']
    if incomplete:
        out += [f"**NON-INFORMATIVE (D9):** the excluded block is not known to be complete "
                f"({'; '.join(incomplete)}); the numbers below are shown for traceability only.", '']
    out += ['| Contrast | Estimate (pp) | 95% CI (HC3) | K evaluable / df | Decision | '
            'Coarse class: sensitivity vs primary | Agrees |', '|---|---|---|---|---|---|---|']
    for key, label in (('H1_PRIMARY_W_A_minus_N', 'W, A − N'),
                       ('H2_SPECIFICITY_W_A_minus_P', 'W, A − P')):
        h95 = g(key, 'HC3_95')
        d_s, d_p = g(key, 'decision'), gp(key, 'decision')
        dec = f'non-informative (truncation) [{d_s}]' if incomplete else reported(d_s, floor)
        agree = '—' if incomplete else ('yes' if coarse(d_s) == coarse(d_p) else 'no')
        out.append(f"| {label} | {pp(h95['estimate'])} | {ci(h95['ci'])} | {keval(h95)} | {dec} | "
                   f"{coarse(d_s)} vs {coarse(d_p)} | {agree} |")
    hs = 'EXPLORATORY_heterogeneity_and_stability'
    lofo = prim[hs]['leave_one_family_out']
    rng = gp(hs, 'leave_one_family_out_range')
    for f in fams:
        e = gp(hs, 'leave_one_family_out', f) if f in lofo else None
        est = None if not e or 'estimate' not in e else e['estimate']
        h1 = a['H1_PRIMARY_W_A_minus_N']['HC3_95']['estimate']
        same = '—' if est is None or len(fams) != 1 else \
            ('yes' if abs(est - h1) < 1e-9 else 'NO (check the derivation)')
        out += ['', f"Primary leave-one-family-out entry for {f}: "
                f"{pp(est)} pp ({(e or {}).get('decision', (e or {}).get('status', '—'))}); "
                f"equals the sensitivity H1: {same}; "
                f"LOFO range over {gp(hs, 'n_families')} sectors "
                f"{'—' if rng is None else f'[{pp(rng[0])}, {pp(rng[1])}]'} pp."]
    return out


def truncation_table(res, src):
    p = res / 'truncation_report.json'
    if not p.exists():
        return []
    t = json.loads(p.read_text())
    g = lambda *k: src.get(p, t, k)
    out = ['', f"Blocks complete: K in complete blocks = {g('K_in_complete_blocks')} of "
           f"{g('K_scheduled')}; closed-out runs {g('closed_out_runs')}; analysis flag "
           f"`{g('analysis_flag') or 'none'}`.", '', '| Sector | State | Scheduled | Closed out |',
           '|---|---|---|---|']
    for i, b in enumerate(t['blocks']):
        out.append(f"| {g('blocks', i, 'family')} | {g('blocks', i, 'state')} | "
                   f"{g('blocks', i, 'scheduled')} | {g('blocks', i, 'closed_out')} |")
    return out


def gate_table(res, src):
    p = res / 'gate_output.json'
    if not p.exists():
        return []
    d = json.loads(p.read_text())
    g = lambda *k: src.get(p, d, k)
    pol = d['policies']
    out = ['', f"Review gate (natural policy; evaluable rows {g('n_rows_evaluable')}, "
           f"excluded {g('n_rows_missing_excluded')}).", '',
           '| Detector | Accepted risk E[U(1−G)] (%) | Detection of U (%) | Safe retained (%) | Review load among passing (%) | not_evaluable (%) |',
           '|---|---|---|---|---|---|']
    for det in [k for k in pol if isinstance(pol[k], dict) and 'by_mechanism' in pol[k]] + ['tests_only']:
        m = pol[det]
        val = lambda k: g('policies', det, k) if k in m else None
        out.append(f"| {det} | {pp(val('U_accepted'))} | {pp(val('detection_of_U'))} | "
                   f"{pp(val('S_retention_rate'))} | "
                   f"{pp(val('review_load_among_passing'))} | "
                   f"{pp(val('not_evaluable_rate_among_passing'))} |")
    if 'paired_difference' in d:
        out += ['', f"Paired sector bootstrap, GSC − AST: "
                f"{json.dumps(g('paired_difference'))}"]
    return out


def witness_table(wdir, src):
    p = Path(wdir) / 'witness_summary.json'
    t = json.loads(p.read_text())
    out = ['', 'Detectors on admission witnesses (framing N; counts alert / no_alert / not_evaluable).',
           '', '| Mechanism | Patch | GSC | AST | except |', '|---|---|---|---|---|']
    for mech in ('M1', 'M2', 'M3'):
        for kind in ('s_plus', 'u_plus', 'alt_safe', 'weak_variant', 'canary_break'):
            cells = []
            for det in ('gsc', 'ast', 'except_local'):
                c = src.get(p, t, (f'{mech}|{kind}|{det}',))
                cells.append(f"{c['alert']}/{c['no_alert']}/{c['not_evaluable']}")
            out.append(f'| {mech} | {kind} | ' + ' | '.join(cells) + ' |')
    pj = Path(wdir) / 'witness_detectors.jsonl'
    if pj.exists():          # every safe alternative the GSC flags is named, with its depths
        rows = [json.loads(l) for l in pj.read_text(encoding='utf-8').splitlines() if l.strip()]
        for i, r in enumerate(rows):
            if r['patch'] == 'alt_safe' and r['states'].get('gsc') == 'alert':
                st = src.get(pj, {f'line {i + 1}': r}, (f'line {i + 1}', 'states'))
                out += ['', f"GSC (depth 2) alert on a safe alternative: {r['template_id']} "
                        f"(depth 1 {st.get('gsc_d1')}, depth 3 {st.get('gsc_d3')}; flagged "
                        f"{', '.join(r['reasons'].get('gsc', []))}). A detector false positive, "
                        f"not a label: the oracle scores this patch safe."]
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--results')
    ap.add_argument('--freeze', help='the frozen manifest (required with --results: the D9 '
                    'sensitivity section is driven by the freeze)')
    ap.add_argument('--witnesses')
    ap.add_argument('--out', required=True)
    a = ap.parse_args(argv)
    src, lines = Src(), ['# TwinGuard tables (generated; do not edit by hand)', '']
    if a.results:
        if not a.freeze:
            ap.error('--results needs --freeze (the D9 sensitivity section reads the freeze)')
        res = Path(a.results)
        fz = json.loads(Path(a.freeze).read_text())
        lines += (main_tables(res, src) + sensitivity_table(res, src, fz) + truncation_table(res, src)
                  + gate_table(res, src))
    if a.witnesses:
        lines += witness_table(a.witnesses, src)
    lines += ['', '## Provenance', '', '| File | JSON path | Value |', '|---|---|---|']
    lines += [f'| {f} | `{k}` | `{json.dumps(v)}` |' for f, k, v in src.rows]
    Path(a.out).write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps({'out': a.out, 'numbers_with_source': len(src.rows)}))


if __name__ == '__main__':
    main()
