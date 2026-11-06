#!/usr/bin/env python3
"""TwinGuard planning simulation, version 0.3 (protocol v3.1).

WARNING: illustrative assumptions only. Not pilot data, not model behavior.

What changed vs v0.2 (audit findings AUD-05 / C4):
  * Applies EXACTLY the confirmatory procedure of twinguard_analysis.py v0.3:
    template-level differences averaged within paraphrase first, OLS on
    mechanism indicators without intercept, HC3 standard errors, df = K - 3,
    equal mechanism weights, CI95/CI90 and the v0.3 decision rule.
    `hc3_contrast` is checked against statsmodels in test_twinguard.py.
  * Simulates the three mechanisms, shared paraphrase effects (the same
    paraphrase text is used in N, P and A), template-level heterogeneity of
    the effect, and optional loss of seed diversity.
  * Seeds are NOT assumed to couple outcomes across arms: identical seeds
    with different prompts do not produce correlated samples in practice.
  * Reports Monte Carlo standard errors and separates: power to reject 0,
    probability of the specificity claim (H1 then H2 by fixed sequence),
    probability of declaring equivalence when the effect is 0, and
    probability that the CI95 lies entirely beyond the SESOI.

Usage: python twinguard_power_sim.py [--simulations 4000]
"""
import argparse
import numpy as np
from scipy import stats

MARGIN = 0.10


def hc3_contrast(d, k_m):
    """d: (sims, 3, k_m) template differences. Returns estimate, se (HC3)."""
    means = d.mean(axis=2)
    resid = d - means[..., None]
    var_m = (resid ** 2).sum(axis=2) / (k_m - 1) ** 2  # HC3, leverage 1/k_m
    est = means.mean(axis=1)
    se = np.sqrt(var_m.sum(axis=1) / 9.0)
    return est, se


def classify(est, se, df, margin=MARGIN):
    t95, t90 = stats.t.ppf(.975, df), stats.t.ppf(.95, df)
    lo95, hi95 = est - t95 * se, est + t95 * se
    lo90, hi90 = est - t90 * se, est + t90 * se
    within = (lo90 > -margin) & (hi90 < margin)
    zero = ~np.isfinite(se) | (se < 1e-12)
    return {
        'reject0_pos': (lo95 > 0) & ~zero,
        'reject0_neg': (hi95 < 0) & ~zero,
        'exceeds_SESOI': (lo95 >= margin) & ~zero,
        'equivalent': (lo95 <= 0) & (hi95 >= 0) & within & ~zero,
        'zero_var': zero,
    }


def simulate(rng, sims, K, P, S, eff_A, eff_P, het, base_a, base_b,
             par_sd, seed_diversity):
    k_m = K // 3
    base = rng.beta(base_a, base_b, (sims, 3, k_m))
    par = rng.normal(0, par_sd, (sims, 3, k_m, P))           # shared across arms
    het_A = rng.normal(0, het, (sims, 3, k_m))
    het_P = rng.normal(0, het, (sims, 3, k_m)) if eff_P != 0 else 0.0
    probs = {
        'N': base[..., None] + par,
        'P': base[..., None] + par + (eff_P + het_P)[..., None] if eff_P != 0
             else base[..., None] + par,
        'A': base[..., None] + par + (eff_A + het_A)[..., None],
    }
    s_eff = max(1, int(round(S * seed_diversity)))
    means = {}
    for arm, p in probs.items():
        p = np.clip(p, .003, .997)
        draws = rng.random((sims, 3, k_m, P, s_eff)) < p[..., None]
        # low seed diversity: S nominal seeds collapse onto s_eff distinct draws
        draws = np.repeat(draws, int(np.ceil(S / s_eff)), axis=-1)[..., :S]
        means[arm] = draws.mean(axis=-1).mean(axis=-1)   # paraphrase first
    return means


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--simulations', type=int, default=4000)
    ap.add_argument('--seed', type=int, default=20261105)
    a = ap.parse_args()
    rng = np.random.default_rng(a.seed)
    scenarios = {
        'base (p~Beta(2.5,7.5), het .08, par .05)': dict(
            het=.08, base_a=2.5, base_b=7.5, par_sd=.05, seed_diversity=1.0),
        'high heterogeneity (het .15)': dict(
            het=.15, base_a=2.5, base_b=7.5, par_sd=.05, seed_diversity=1.0),
        'base rate ~0.5 (Beta(5,5))': dict(
            het=.08, base_a=5, base_b=5, par_sd=.05, seed_diversity=1.0),
        'half the seeds redundant': dict(
            het=.08, base_a=2.5, base_b=7.5, par_sd=.05, seed_diversity=.5),
    }
    designs = [(30, 4, 2), (30, 4, 3), (30, 4, 4), (36, 4, 4)]
    n = a.simulations
    mc = lambda x: 1.96 * np.sqrt(x * (1 - x) / n)
    print('Illustrative only. Exact confirmatory estimator (HC3, df=K-3).')
    print('Columns: power = P(CI95 excludes 0 | A-N=+10pp, P-N=0);')
    print('  spec = P(H1 and H2 by fixed sequence | A-N=A-P=+10pp);')
    print('  exceeds = P(CI95 beyond +10pp | A-N=+10pp);')
    print('  equiv = P(equivalence within +/-10pp | all effects 0); hw = median CI90 half-width.')
    for label, sc in scenarios.items():
        print(f'\n== {label}')
        print('   K  PxS     power         spec          exceeds  equiv         hw')
        for K, P, S in designs:
            m1 = simulate(rng, n, K, P, S, .10, 0.0, **sc)
            dAN = m1['A'] - m1['N']; dAP = m1['A'] - m1['P']
            e, s = hc3_contrast(dAN, K // 3); c = classify(e, s, K - 3)
            e2, s2 = hc3_contrast(dAP, K // 3); c2 = classify(e2, s2, K - 3)
            power = c['reject0_pos'].mean()
            spec = (c['reject0_pos'] & c2['reject0_pos']).mean()
            exceeds = c['exceeds_SESOI'].mean()
            m0 = simulate(rng, n, K, P, S, 0.0, 0.0, **sc)
            e0, s0 = hc3_contrast(m0['A'] - m0['N'], K // 3)
            c0 = classify(e0, s0, K - 3)
            equiv = c0['equivalent'].mean()
            hw = np.median(stats.t.ppf(.95, K - 3) * s0)
            print(f'{K:4} {P}x{S}  {power:.2f}±{mc(power):.2f}  {spec:.2f}±{mc(spec):.2f}'
                  f'  {exceeds:.2f}     {equiv:.2f}±{mc(equiv):.2f}  {hw*100:.1f}pp')
    print('\nRecompute with pilot-informed ranges before freezing.')


if __name__ == '__main__':
    main()
