#!/usr/bin/env python3
"""TwinGuard planning simulation, version 0.2 (protocol v3.0).

WARNING: illustrative assumptions, not pilot data and not model behavior.

For each design (K templates, R paired rollouts per arm per template) it
reports, under INDEPENDENT sampling across arms (the conservative planning
assumption of protocol v3.0):
  - power of the two-sided test of Delta=0 when the true effect is --effect;
  - probability of declaring equivalence within +/- --margin when the true
    effect is 0 (90% CI fully inside the margin, i.e. TOST at 5%);
  - median half-width of the 90% CI.
Unit of inference: template. Baseline p ~ Beta(2.5, 7.5) (mean 0.25).
Usage: python twinguard_power_sim.py [--simulations 10000] [--effect 0.10]
"""
import argparse
import numpy as np
from scipy import stats


def draw(rng, sims, k, r, effect, het):
    pc = rng.beta(2.5, 7.5, (sims, k))
    pa = np.clip(pc + effect + rng.normal(0, het, (sims, k)), .003, .997)
    d = ((rng.random((sims, k, r)) < pa[..., None]).mean(-1)
         - (rng.random((sims, k, r)) < pc[..., None]).mean(-1))
    m = d.mean(-1)
    se = d.std(-1, ddof=1) / np.sqrt(k)
    return m, se


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--simulations', type=int, default=10000)
    ap.add_argument('--effect', type=float, default=0.10)
    ap.add_argument('--margin', type=float, default=0.10)
    ap.add_argument('--heterogeneity', type=float, default=0.08)
    ap.add_argument('--seed', type=int, default=20261105)
    a = ap.parse_args()
    print('Illustrative only. Independent sampling across arms.')
    print(f'effect={a.effect:+.2f} margin=+/-{a.margin:.2f} '
          f'heterogeneity SD={a.heterogeneity:.2f}')
    print('   K   R   power(effect)   P(equiv | 0)   median CI90 half-width')
    for k, r in ((30, 6), (30, 8), (48, 6), (48, 8)):
        rng = np.random.default_rng(a.seed + 100 * k + r)
        m, se = draw(rng, a.simulations, k, r, a.effect, a.heterogeneity)
        power = np.mean(np.abs(m / se) > stats.t.ppf(.975, k - 1))
        m0, se0 = draw(rng, a.simulations, k, r, 0.0, a.heterogeneity)
        t90 = stats.t.ppf(.95, k - 1)
        eq = np.mean((m0 - t90 * se0 > -a.margin) & (m0 + t90 * se0 < a.margin))
        print(f'{k:4} {r:3} {power:15.2f} {eq:14.2f} {np.median(t90 * se0):24.3f}')
    print('\nRecompute with pilot-informed ranges before freezing. Repeated')
    print('rollouts reduce within-template noise; they never add templates.')


if __name__ == '__main__':
    main()
