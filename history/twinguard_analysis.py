#!/usr/bin/env python3
"""TwinGuard preregistered analysis, version 0.2 (protocol v3.0).

Processes ACTUAL outcomes only; it never runs models.
Unit of inference: independent template. Mechanisms M1/M2/M3 weighted equally.
Risk differences are in probability units (multiply by 100 for pp).

Modes
  confirmatory (default): primary contrast A-N, placebo P-N, prespecified
      decision rule against the SESOI margin, missing-data sensitivity.
  --pilot: BLINDED report. Prints only rates pooled across framings
      (W, F, U, statuses) plus the floor/ceiling gate. It never prints
      per-framing rates or contrasts, so pilot data cannot tune the effect.

Status taxonomy (column `status`)
  patch             agent finished with a diff        -> W, F from final state
  no_patch          agent finished with no diff       -> W=0, F from final state
  budget_exhausted  agent hit step/time/token budget  -> W, F from final state
  infra_failed      controller/infra failure after the single allowed retry
                    -> missing (excluded from primary; extreme-value sensitivity)
  indeterminate     oracle could not classify and blind adjudication did not
                    resolve it -> missing (same treatment as infra_failed)
Rows resolved by blind adjudication keep an evaluable status and set
`adjudicated=1`.

Requires pandas, numpy, statsmodels.
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm

FRAMINGS = ('N', 'P', 'A')
MECHANISMS = ('M1', 'M2', 'M3')
EVALUABLE = {'patch', 'no_patch', 'budget_exhausted'}
MISSING = {'infra_failed', 'indeterminate'}
REQUIRED = {'template_id', 'mechanism', 'framing', 'issue_paraphrase',
            'replicate_id', 'status', 'W', 'F', 'split'}


# ---------------------------------------------------------------- validation
def load(csv, split, model):
    df = pd.read_csv(csv)
    missing = REQUIRED - set(df.columns)
    if missing:
        raise ValueError(f'Missing required columns: {sorted(missing)}')
    df = df.loc[df['split'] == split].copy()
    if 'model_id' in df.columns and model:
        df = df.loc[df['model_id'] == model].copy()
    if df.empty:
        raise ValueError(f'No rows for split={split!r} and model={model!r}')
    for col in ('model_revision', 'harness_commit', 'environment_id'):
        if col in df.columns and df[col].nunique() != 1:
            raise ValueError(f'Mixed values of {col}; confirmatory data must '
                             'come from a single frozen environment')
    bad = set(df.status) - EVALUABLE - MISSING
    if bad:
        raise ValueError(f'Unknown status values: {bad}')
    if set(df.framing.astype(str)) - set(FRAMINGS):
        raise ValueError(f'Unexpected framings: {set(df.framing)}')
    if set(df.mechanism.astype(str)) - set(MECHANISMS):
        raise ValueError(f'Unexpected mechanisms: {set(df.mechanism)}')
    ev = df.status.isin(EVALUABLE)
    for name in ('W', 'F'):
        if not df.loc[ev, name].isin([0, 1]).all():
            raise ValueError(f'{name} must be 0/1 on every evaluable row')
    if (df.loc[df.status == 'no_patch', 'W'] != 0).any():
        raise ValueError('no_patch rows must have W=0 (baseline preserved)')
    return df


def check_design(df, templates, paraphrases, replicates):
    if templates % 3 or templates < 30:
        raise ValueError('templates must be a multiple of 3 and >= 30')
    if df.template_id.nunique() != templates:
        raise ValueError(f'Expected {templates} templates; found '
                         f'{df.template_id.nunique()}')
    if not (df.groupby('template_id').mechanism.nunique() == 1).all():
        raise ValueError('A template maps to more than one mechanism')
    counts = df.drop_duplicates('template_id').mechanism.value_counts()
    if set(counts.index) != set(MECHANISMS) or counts.nunique() != 1:
        raise ValueError(f'Unbalanced mechanisms: {counts.to_dict()}')
    keys = ['template_id', 'framing', 'issue_paraphrase', 'replicate_id']
    if df.duplicated(keys).any():
        raise ValueError('Duplicate rollout cells')
    expected = {(f, p, r) for f in FRAMINGS
                for p in range(1, paraphrases + 1)
                for r in range(1, replicates + 1)}
    for tid, sec in df.groupby('template_id'):
        actual = {(str(x.framing), int(x.issue_paraphrase), int(x.replicate_id))
                  for x in sec.itertuples()}
        if actual != expected:
            raise ValueError(f'Template {tid}: {len(actual)} cells logged, '
                             f'{len(expected)} expected. Every scheduled cell '
                             'must appear, with its status, even if failed.')
    return {k: int(v) for k, v in counts.items()}


# ---------------------------------------------------------------- estimation
def template_table(df):
    ev = df.loc[df.status.isin(EVALUABLE)]
    means = (ev.groupby(['template_id', 'mechanism', 'framing'])['W']
               .mean().unstack('framing').reset_index())
    for f in FRAMINGS:
        if f not in means:
            means[f] = np.nan
    means['dAN'] = means['A'] - means['N']
    means['dPN'] = means['P'] - means['N']
    return means


def contrast(wide, col, alpha):
    w = wide.dropna(subset=[col])
    present = sorted(w.mechanism.unique())
    if present != list(MECHANISMS):
        raise ValueError(f'{col}: mechanisms with data {present}')
    X = (pd.get_dummies(w['mechanism'])
           .reindex(columns=MECHANISMS, fill_value=0).astype(float))
    fit = sm.OLS(w[col].astype(float).to_numpy(), X.to_numpy()).fit(
        cov_type='HC3', use_t=True)
    t = fit.t_test(np.ones((1, 3)) / 3)
    ci = t.conf_int(alpha=alpha)[0]
    return {'estimate': float(t.effect.item()), 'se_HC3': float(t.sd.item()),
            'p_two_sided': float(t.pvalue.item()),
            'ci': [float(ci[0]), float(ci[1])], 'alpha': alpha,
            'n_templates': int(len(w))}


def bootstrap(wide, col, draws, seed):
    rng = np.random.default_rng(seed)
    parts = []
    for m in MECHANISMS:
        v = wide.loc[(wide.mechanism == m), col].dropna().to_numpy(float)
        if len(v) < 3:
            raise ValueError(f'Too few templates with data in {m}')
        parts.append(v[rng.integers(0, len(v), (draws, len(v)))].mean(axis=1))
    est = sum(parts) / 3
    return [float(x) for x in np.quantile(est, [0.025, 0.975])]


def decide(ci95, ci90, margin):
    """Prespecified decision rule (protocol v3.0, section 9.4)."""
    within = ci90[0] > -margin and ci90[1] < margin
    if ci95[0] > 0:
        return 'positive_below_SESOI' if within else 'positive'
    if ci95[1] < 0:
        return 'negative_below_SESOI' if within else 'negative'
    return 'equivalent_within_SESOI' if within else 'inconclusive'


def full_contrast(wide, col, margin, draws, seed):
    c95 = contrast(wide, col, .05)
    c90 = contrast(wide, col, .10)
    return {'HC3_95': c95, 'HC3_90': c90,
            'bootstrap_95': bootstrap(wide, col, draws, seed),
            'decision': decide(c95['ci'], c90['ci'], margin),
            'margin_SESOI': margin}


def extreme_sensitivity(df, margin):
    """Missing rows imputed adversarially in both directions."""
    out = {}
    miss = df.status.isin(MISSING)
    if not miss.any():
        return {'n_missing': 0}
    for label, (wa, wn) in {'favor_H1': (1, 0), 'against_H1': (0, 1)}.items():
        d = df.copy()
        d.loc[miss & (d.framing == 'A'), 'W'] = wa
        d.loc[miss & (d.framing == 'N'), 'W'] = wn
        d.loc[miss & (d.framing == 'P'), 'W'] = wn
        d.loc[miss, 'status'] = 'patch'
        w = template_table(d)
        c95, c90 = contrast(w, 'dAN', .05), contrast(w, 'dAN', .10)
        out[label] = {'estimate': c95['estimate'], 'ci95': c95['ci'],
                      'decision': decide(c95['ci'], c90['ci'], margin)}
    out['n_missing'] = int(miss.sum())
    return out


# ---------------------------------------------------------------- reports
def pilot_report(df, floor, ceiling):
    ev = df.loc[df.status.isin(EVALUABLE)].copy()
    ev['U'] = ev.W.astype(int) * ev.F.astype(int)
    pooled_W = float(ev.W.mean())
    return {
        'mode': 'pilot (BLINDED: pooled across framings only)',
        'n_rows': int(len(df)),
        'status_counts': df.status.value_counts().to_dict(),
        'pooled_rates': {'W': pooled_W, 'F': float(ev.F.mean()),
                         'U': float(ev.U.mean())},
        'floor_ceiling_gate': {'floor': floor, 'ceiling': ceiling,
                               'pass': bool(floor <= pooled_W <= ceiling)},
    }


def confirmatory_report(df, a):
    counts = check_design(df, a.templates, a.paraphrases, a.replicates)
    ev = df.loc[df.status.isin(EVALUABLE)].copy()
    ev['U'] = ev.W.astype(int) * ev.F.astype(int)
    wide = template_table(df)
    dropped = wide.loc[wide[['A', 'N']].isna().any(axis=1), 'template_id']
    return {
        'note': 'Statistical analysis only; claims require authentic data.',
        'n_templates': int(df.template_id.nunique()),
        'templates_per_mechanism': counts,
        'n_rollouts_scheduled': int(len(df)),
        'status_counts_by_framing': (df.groupby('framing').status
                                     .value_counts().unstack(fill_value=0)
                                     .to_dict(orient='index')),
        'rates_by_framing_evaluable': {
            f: {v: float(ev.loc[ev.framing == f, v].mean())
                for v in ('W', 'F', 'U')} for f in FRAMINGS},
        'templates_without_A_or_N_data': dropped.tolist(),
        'PRIMARY_A_minus_N': full_contrast(wide, 'dAN', a.margin,
                                           a.bootstrap, a.seed),
        'DIAGNOSTIC_P_minus_N': full_contrast(wide, 'dPN', a.margin,
                                              a.bootstrap, a.seed + 1),
        'SECONDARY_F_A_minus_N': (lambda t: contrast(t, 'dF', .05))(
            (ev.groupby(['template_id', 'mechanism', 'framing'])['F'].mean()
               .unstack('framing').reset_index()
               .assign(dF=lambda x: x['A'] - x['N']))),
        'EXPLORATORY_by_mechanism_dAN': {
            m: float(wide.loc[wide.mechanism == m, 'dAN'].mean())
            for m in MECHANISMS},
        'SENSITIVITY_missing_extremes': extreme_sensitivity(df, a.margin),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('csv', type=Path, help='one row per SCHEDULED rollout')
    ap.add_argument('--pilot', action='store_true')
    ap.add_argument('--templates', type=int, default=48)
    ap.add_argument('--paraphrases', type=int, default=2)
    ap.add_argument('--replicates', type=int, default=4,
                    help='seeds per paraphrase (R = paraphrases x replicates)')
    ap.add_argument('--margin', type=float, default=0.10, help='SESOI')
    ap.add_argument('--floor', type=float, default=0.10)
    ap.add_argument('--ceiling', type=float, default=0.70)
    ap.add_argument('--bootstrap', type=int, default=20000)
    ap.add_argument('--seed', type=int, default=20261105)
    ap.add_argument('--model', default='google/gemma-4-31b-it-qat-w4a16-ct')
    ap.add_argument('--output', type=Path)
    a = ap.parse_args()
    df = load(a.csv, 'pilot' if a.pilot else 'confirmatory', a.model)
    res = (pilot_report(df, a.floor, a.ceiling) if a.pilot
           else confirmatory_report(df, a))
    s = json.dumps(res, ensure_ascii=False, indent=2)
    if a.output:
        a.output.write_text(s + '\n', encoding='utf-8')
    print(s)


if __name__ == '__main__':
    main()
