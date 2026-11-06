# Reemplazo para _within_template_var y generalization en twinguard_analysis.py (L408-L467)

def _within_template_var(df):
    """Unbiased within-template sampling variance of each template's paired A-N
    difference, estimated directly from the sample variance across shared
    paraphrases: s^2_{d_i} / Q_i."""
    ev = df.loc[df.status.isin(EVALUABLE) & df.framing.isin(['A', 'N'])]
    by_par = (ev.groupby(['template_id', 'issue_paraphrase', 'framing']).W
                .mean().unstack('framing').dropna())
    d_par = by_par['A'] - by_par['N']
    out = {}
    for tid, s in d_par.groupby(level=0):
        out[tid] = float(s.var(ddof=1) / len(s)) if len(s) > 1 else 0.0
    return pd.Series(out)


def generalization(df, wW, primary_decision):
    w = wW.dropna(subset=['dAN']).set_index('template_id')
    k = len(w)
    mech_means = w.groupby('mechanism').dAN.mean()
    resid = w.dAN - w.mechanism.map(mech_means)
    s2 = float((resid ** 2).sum() / (k - 3))
    v = _within_template_var(df).reindex(w.index)
    v_mean = float(v.mean()) if not v.dropna().empty else 0.0
    tau2 = max(0.0, s2 - v_mean)
    se_m2 = (w.groupby('mechanism').dAN.var(ddof=1)
               / w.groupby('mechanism').dAN.count())
    sigma2_mech = max(0.0, float(mech_means.var(ddof=1)) - float(se_m2.mean()))
    c = contrast(wW, 'dAN', .05)
    t = stats.t.ppf(.975, k - 3)
    half_latent = t * np.sqrt(c['se'] ** 2 + tau2 + sigma2_mech)
    half_observed = t * np.sqrt(c['se'] ** 2 + s2 + sigma2_mech)
    lofo = {}
    for fam in sorted(wW.family.unique()):
        sub = wW.loc[wW.family != fam]
        try:
            c95 = contrast(sub, 'dAN', .05, min_per_mech=2)
            c90 = contrast(sub, 'dAN', .10, min_per_mech=2)
            lofo[fam] = {'estimate': c95['estimate'], 'decision': decide(c95, c90)}
        except DesignError as exc:
            lofo[fam] = {'error': str(exc)}
    ok = [x for x in lofo.values() if 'decision' in x]
    return {
        'note': 'Exploratory. Does not alter H1/H2.',
        'prediction_interval_95_new_template': [c['estimate'] - half_latent,
                                                c['estimate'] + half_latent],
        'prediction_interval_95_observed_new_template': [c['estimate'] - half_observed,
                                                         c['estimate'] + half_observed],
        'tau2_between_templates': tau2,
        'sigma2_between_mechanisms': sigma2_mech,
        'mean_within_template_sampling_var': v_mean,
        'share_templates_positive_negative_zero': [
            float((w.dAN > 0).mean()), float((w.dAN < 0).mean()),
            float((w.dAN == 0).mean())],
        'leave_one_family_out': lofo,
        'leave_one_family_out_range': [min(x['estimate'] for x in ok),
                                       max(x['estimate'] for x in ok)] if ok else None,
        'leave_one_family_out_same_class': int(sum(
            coarse(x['decision']) == coarse(primary_decision) for x in ok)),
        'n_families': int(wW.family.nunique()),
    }
