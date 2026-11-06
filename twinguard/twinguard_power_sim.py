#!/usr/bin/env python3
"""TwinGuard planning simulation, version 0.5 (protocol v3.3).

WARNING: illustrative assumptions only. Not pilot data, not model behavior.

Changes vs v0.3 (third review, findings H04/H05):
  * No clipping. All random components are bounded (Rademacher +/- sd) and
    the baseline is rescaled into a range where every probability is valid,
    so the marginal effect equals the nominal effect EXACTLY (a nominal null
    is a true null). The generator asserts this.
  * Optional family component: a framing effect shared by the three
    templates of the same family (one per mechanism), plus an idiosyncratic
    component. Both the HC3 analysis and the family-clustered sensitivity
    (CR1, df = G-1, as statsmodels computes it) are evaluated.
  * Sampling across framings is planned as CONDITIONALLY INDEPENDENT given
    the template. This is a planning assumption, not an established fact:
    shared seeds could induce dependence depending on the inference engine.

v0.5 (Argon 4, R3-06 and section E): two nulls are reported. The
'average null' keeps template-level heterogeneity of the A effect around a
zero mean (conservative); the 'sharp null' sets p_A = p_N for every
template. Two adverse scenarios added: a placebo that absorbs part of the
effect (A-P smaller than A-N) and a paraphrase x framing interaction.

Exactly the confirmatory estimator: paraphrase-first means, template
differences, OLS on mechanism indicators, HC3, df = K-3, equal mechanism
weights, v0.4 decision rule. Checked against statsmodels in the tests.
"""
import argparse
import numpy as np
from scipy import stats

MARGIN = 0.10


def hc3_contrast(d, k_m):
    """d: (sims, 3, k_m) template differences -> estimate, HC3 se."""
    means = d.mean(axis=2)
    resid = d - means[..., None]
    var_m = (resid ** 2).sum(axis=2) / (k_m - 1) ** 2
    return means.mean(axis=1), np.sqrt(var_m.sum(axis=1) / 9.0)


def cluster_contrast(d, k_m):
    """Family-clustered (CR1) se; family g = template index g in each
    mechanism. Matches statsmodels cov_type='cluster'. df = G - 1."""
    K = 3 * k_m
    resid = d - d.mean(axis=2, keepdims=True)
    scores = resid.sum(axis=1) / (3 * k_m)          # (sims, G)
    factor = k_m / (k_m - 1) * (K - 1) / (K - 3)
    return d.mean(axis=2).mean(axis=1), np.sqrt(factor * (scores ** 2).sum(axis=1))


def classify(est, se, df, margin=MARGIN):
    t95, t90 = stats.t.ppf(.975, df), stats.t.ppf(.95, df)
    lo95, hi95 = est - t95 * se, est + t95 * se
    lo90, hi90 = est - t90 * se, est + t90 * se
    zero = ~np.isfinite(se) | (se < 1e-12)
    within = (lo90 > -margin) & (hi90 < margin)
    return {'reject0_pos': (lo95 > 0) & ~zero,
            'reject0_neg': (hi95 < 0) & ~zero,
            'exceeds_SESOI': (lo95 >= margin) & ~zero,
            'equivalent': (lo95 <= 0) & (hi95 >= 0) & within & ~zero,
            'zero_var': zero}


def simulate(rng, sims, K, P, S, eff_A, eff_P, het, base_a, base_b,
             par_sd, seed_diversity, family_sd=0.0, pxf_sd=0.0,
             sharp_null=False):
    """Returns template x framing means (paraphrase first), shape (sims,3,k_m).
    het / family_sd / par_sd are SDs of bounded Rademacher components."""
    k_m = K // 3
    if sharp_null and eff_A == 0 and eff_P == 0:
        het, family_sd, pxf_sd = 0.0, 0.0, 0.0
    bound = par_sd + het + family_sd + pxf_sd
    lo = bound + max(0.0, -min(eff_A, eff_P))
    hi = 1 - bound - max(0.0, eff_A, eff_P)
    if not lo < hi:
        raise ValueError('components too large for valid probabilities')
    base = lo + (hi - lo) * rng.beta(base_a, base_b, (sims, 3, k_m))
    rad = lambda shape: rng.choice([-1.0, 1.0], size=shape)
    par = par_sd * rad((sims, 3, k_m, P))
    fam = family_sd * rad((sims, 1, k_m)) if family_sd else 0.0
    slope_A = eff_A + het * rad((sims, 3, k_m)) + fam
    pxf = pxf_sd * rad((sims, 3, k_m, P)) if pxf_sd else 0.0
    slope_P = (eff_P + het * rad((sims, 3, k_m)) + fam) if eff_P else 0.0
    p = {'N': base[..., None] + par,
         'P': base[..., None] + par + np.asarray(slope_P)[..., None]
              if eff_P else base[..., None] + par,
         'A': base[..., None] + par + slope_A[..., None] + pxf}
    s_eff = max(1, int(round(S * seed_diversity)))
    out = {}
    for arm, q in p.items():
        assert (q >= 0).all() and (q <= 1).all(), 'probability out of [0,1]'
        draws = rng.random((sims, 3, k_m, P, s_eff)) < q[..., None]
        draws = np.repeat(draws, int(np.ceil(S / s_eff)), axis=-1)[..., :S]
        out[arm] = draws.mean(axis=-1).mean(axis=-1)
    return out


SCENARIOS = {
    'base (het 8pp, no family effect)':
        dict(het=.08, family_sd=0.0, base_a=2.5, base_b=7.5, seed_diversity=1.0),
    'high heterogeneity (het 15pp)':
        dict(het=.15, family_sd=0.0, base_a=2.5, base_b=7.5, seed_diversity=1.0),
    'family-shared effect (fam 8pp + idio 8pp)':
        dict(het=.08, family_sd=.08, base_a=2.5, base_b=7.5, seed_diversity=1.0),
    'strong family effect (fam 12pp + idio 8pp; Astra scenario)':
        dict(het=.08, family_sd=.12, base_a=2.5, base_b=7.5, seed_diversity=1.0),
    'baseline near 0.5':
        dict(het=.08, family_sd=0.0, base_a=5, base_b=5, seed_diversity=1.0),
    'half the seeds redundant':
        dict(het=.08, family_sd=0.0, base_a=2.5, base_b=7.5, seed_diversity=.5),
    'paraphrase x framing interaction 8pp + het 12pp (Argon scenario)':
        dict(het=.12, family_sd=0.0, pxf_sd=.08, base_a=2.5, base_b=7.5,
             seed_diversity=1.0),
    'placebo absorbs 4pp (A-N=10, P-N=4, A-P=6; Argon scenario)':
        dict(het=.08, family_sd=0.0, base_a=2.5, base_b=7.5, seed_diversity=1.0,
             eff_P=.04),
}


def evaluate(rng, n, K, P, S, sc):
    sc = dict(sc)
    eff_P = sc.pop('eff_P', 0.0)
    k = K // 3
    out = {}
    m = simulate(rng, n, K, P, S, .10, eff_P, par_sd=.05, **sc)
    m0 = simulate(rng, n, K, P, S, 0.0, 0.0, par_sd=.05, **sc)
    ms = simulate(rng, n, K, P, S, 0.0, 0.0, par_sd=.05, sharp_null=True, **sc)
    for name, fn, df in (('HC3', hc3_contrast, K - 3),
                         ('family-CR1', cluster_contrast, k - 1)):
        c = classify(*fn(m['A'] - m['N'], k), df)
        c2 = classify(*fn(m['A'] - m['P'], k), df)
        c0 = classify(*fn(m0['A'] - m0['N'], k), df)
        cs = classify(*fn(ms['A'] - ms['N'], k), df)
        out[name] = {'H1': c['reject0_pos'].mean(),
                     'H1H2': (c['reject0_pos'] & c2['reject0_pos']).mean(),
                     'type1': (c0['reject0_pos'] | c0['reject0_neg']).mean(),
                     'equiv': c0['equivalent'].mean(),
                     'type1_sharp': (cs['reject0_pos'] | cs['reject0_neg']).mean(),
                     'equiv_sharp': cs['equivalent'].mean(),
                     'null_mean_pp': 100 * (m0['A'] - m0['N']).mean()}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--simulations', type=int, default=4000)
    ap.add_argument('--seed', type=int, default=20261105)
    a = ap.parse_args()
    rng = np.random.default_rng(a.seed)
    n = a.simulations
    print('Illustrative only. Exact confirmatory estimator; no clipping.')
    print('H1 = P(reject 0 | A-N=+10pp, P-N=0); H1H2 = P(H1 and H2 | A-N=A-P=+10pp);')
    print('type1/equiv: average null (heterogeneous A effect, mean 0);')
    print('t1_sh/eq_sh: sharp null (p_A = p_N for every template).')
    print(f'Monte Carlo 95% half-width <= {1.96 * np.sqrt(.25 / n):.3f}.')
    for label, sc in SCENARIOS.items():
        print(f'\n== {label}')
        print('   K  PxS  analysis     H1    H1H2  type1  equiv  t1_sh  eq_sh  null mean')
        for K, P, S in ((30, 4, 4),):
            r = evaluate(rng, n, K, P, S, sc)
            for meth, v in r.items():
                print(f'{K:4} {P}x{S}  {meth:10} {v["H1"]:.2f}  {v["H1H2"]:.2f}'
                      f'  {v["type1"]:.3f}  {v["equiv"]:.2f}  {v["type1_sharp"]:.3f}'
                      f'  {v["equiv_sharp"]:.2f}  {v["null_mean_pp"]:+.2f}pp')


if __name__ == '__main__':
    main()
