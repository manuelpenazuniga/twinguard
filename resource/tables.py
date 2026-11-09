"""Writeup tables (WP14): every number comes from a results file and carries its source.

Reads a results directory written by runner/analyze.py (analysis_output.json,
truncation_report.json, gate_output.json) and, optionally, the witness table of
runner/secondary.py. Writes Markdown tables and a provenance list: for each cell, the file,
the JSON path and the raw value. Nothing is computed here except rounding and
percent formatting; a number without a source is never printed.

  python resource/tables.py --results results/confirmatory [--witnesses results/witnesses] \
      --out results/tables.md
"""
import argparse
import json
from pathlib import Path


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


def main_tables(res, src):
    p = res / 'analysis_output.json'
    a = json.loads(p.read_text())
    g = lambda *k: src.get(p, a, k)
    out = [f"Analysis status: **{g('analysis_status')}**; templates {g('n_templates')}; "
           f"rollouts scheduled {g('n_rollouts_scheduled')}.", '',
           '| Framing | W (%) | F (%) | U (%) | M (%) |', '|---|---|---|---|---|']
    for f in ('N', 'P', 'A'):
        out.append(f'| {f} | ' + ' | '.join(pp(g('rates_template_weighted', f, m))
                                          for m in ('W', 'F', 'U', 'M')) + ' |')
    out += ['', '| Contrast | Estimate (pp) | 95% CI (HC3) | 90% CI | p | Decision |',
            '|---|---|---|---|---|---|']
    for key, label in (('H1_PRIMARY_W_A_minus_N', 'H1: W, A − N'),
                       ('H2_SPECIFICITY_W_A_minus_P', 'H2: W, A − P'),
                       ('DIAGNOSTIC_W_P_minus_N', 'Diagnostic: W, P − N')):
        h95 = g(key, 'HC3_95')
        pv = '—' if h95['p_two_sided'] is None else f"{h95['p_two_sided']:.3f}"
        out.append(f"| {label} | {pp(h95['estimate'])} | {ci(h95['ci'])} | "
                   f"{ci(g(key, 'HC3_90', 'ci'))} | {pv} | {a[key].get('decision', '—')} |")
    out += ['', f"Flags: {json.dumps(g('FLAGS'))}", '']
    out += ['| Mechanism | ΔW A − N (pp, exploratory) |', '|---|---|']
    for m, v in sorted(g('EXPLORATORY_by_mechanism_dAN').items()):
        out.append(f'| {m} | {pp(v)} |')
    return out


def sensitivity_table(res, src):
    p = res / 'analysis_sensitivity.json'
    if not p.exists():
        return []
    a = json.loads(p.read_text())
    g = lambda *k: src.get(p, a, k)
    out = ['', f"Prespecified sensitivity (EXPLORATORY; status {g('analysis_status')}; "
           f"templates {g('n_templates')}): the frozen analysis without the sector(s) of the "
           f"template admitted through an adjudicated auditor false positive. Reported next to "
           f"the primary result, never instead of it.", '',
           '| Contrast | Estimate (pp) | 95% CI (HC3) | Decision |', '|---|---|---|---|']
    for key, label in (('H1_PRIMARY_W_A_minus_N', 'W, A − N'),
                       ('H2_SPECIFICITY_W_A_minus_P', 'W, A − P')):
        h95 = g(key, 'HC3_95')
        out.append(f"| {label} | {pp(h95['estimate'])} | {ci(h95['ci'])} | "
                   f"{a[key].get('decision', '—')} |")
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
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--results')
    ap.add_argument('--witnesses')
    ap.add_argument('--out', required=True)
    a = ap.parse_args(argv)
    src, lines = Src(), ['# TwinGuard tables (generated; do not edit by hand)', '']
    if a.results:
        res = Path(a.results)
        lines += (main_tables(res, src) + sensitivity_table(res, src) + truncation_table(res, src)
                  + gate_table(res, src))
    if a.witnesses:
        lines += witness_table(a.witnesses, src)
    lines += ['', '## Provenance', '', '| File | JSON path | Value |', '|---|---|---|']
    lines += [f'| {f} | `{k}` | `{json.dumps(v)}` |' for f, k, v in src.rows]
    Path(a.out).write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps({'out': a.out, 'numbers_with_source': len(src.rows)}))


if __name__ == '__main__':
    main()
