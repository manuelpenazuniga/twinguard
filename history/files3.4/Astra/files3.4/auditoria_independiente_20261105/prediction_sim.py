"""G1 calibration experiment; synthetic data, no model results.

Vectorizes the exact v0.6 formula, cross-checking one dataset against
generalization(). Coverage refers to a fresh true template effect drawn
uniformly across the THREE FIXED mechanisms and from a new sector.
"""
import json
import sys
from pathlib import Path
import numpy as np
from scipy import stats

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import twinguard_analysis as ta
from test_twinguard import make_df


def formula(a, n):
    # shape repetitions x mechanisms x templates x paraphrases x seeds
    d = (a.mean(axis=-1) - n.mean(axis=-1)).mean(axis=-1)
    mech = d.mean(axis=-1)
    resid = d - mech[..., None]
    s2 = (resid ** 2).sum(axis=(1, 2)) / 27
    se2 = ((resid ** 2).sum(axis=-1) / 81).sum(axis=-1) / 9
    v = 0
    for arm in (a, n):
        ph = (arm.sum(axis=-1) + .5) / 5
        v = v + (ph * (1-ph) / 4).sum(axis=-1) / 16
    tau = np.maximum(0, s2 - v.mean(axis=(1, 2)))
    between = np.maximum(0, mech.var(axis=-1, ddof=1) - (d.var(axis=-1, ddof=1) / 10).mean(axis=-1))
    est = mech.mean(axis=-1)
    half = stats.t.ppf(.975, 27) * np.sqrt(se2 + tau + between)
    return est, half, tau, between, v.mean(axis=(1, 2))


def verify():
    df = make_df()
    arms = []
    for f in ['A', 'N']:
        arr = np.empty((1, 3, 10, 4, 4))
        for m in range(3):
            tids = sorted(df.loc[df.mechanism == f'M{m+1}', 'template_id'].unique())
            for i, tid in enumerate(tids):
                arr[0, m, i] = df.loc[(df.template_id == tid) & (df.framing == f)].sort_values(['issue_paraphrase', 'replicate_id']).W.to_numpy().reshape(4, 4)
        arms.append(arr)
    est, half, tau, between, v = formula(*arms)
    out = ta.generalization(df, ta.template_table(df, 'W'), 'inconclusive')
    np.testing.assert_allclose(out['prediction_interval_95_new_template'], [est[0]-half[0], est[0]+half[0]], atol=1e-12, rtol=0)
    np.testing.assert_allclose(out['tau2_between_templates'], tau[0], atol=1e-12, rtol=0)
    np.testing.assert_allclose(out['sigma2_between_mechanisms'], between[0], atol=1e-12, rtol=0)


def run(label, baseline=.3, mu=.1, tau=.08, family=.0, mechanisms=(0,0,0), coupling='independent', sims=20000):
    rng = np.random.default_rng(20261105)
    shape = (sims, 3, 10)
    rad = lambda s: rng.choice([-1., 1.], size=s)
    theta = mu + tau * rad(shape) + family * rad((sims, 1, 10)) + np.array(mechanisms)[None, :, None]
    pn = np.full(shape + (4, 1), baseline)
    pa = pn + theta[..., None, None]
    assert pa.min() >= 0 and pa.max() <= 1
    u = rng.random(shape + (4, 4))
    n = u < pn
    if coupling == 'independent':
        ua = rng.random(u.shape)
    elif coupling == 'positive':
        ua = u
    else:
        ua = 1-u
    a = ua < pa
    est, half, tauhat, mechhat, vhat = formula(a, n)
    new = mu + tau*rad(sims) + family*rad(sims) + np.array(mechanisms)[rng.integers(3, size=sims)]
    coverage = np.mean((new >= est-half) & (new <= est+half))
    return dict(label=label, sims=sims, baseline=baseline, mu=mu, tau=tau, family=family,
                mechanisms=mechanisms, coupling=coupling, coverage_true=coverage,
                mc_se=np.sqrt(coverage*(1-coverage)/sims),
                mean_tau2=tauhat.mean(), target_tau2=tau*tau+family*family,
                mean_mechanism_variance=mechhat.mean(), target_mechanism_variance=np.var(mechanisms),
                share_tau2_zero=np.mean(tauhat == 0), mean_width=(2*half).mean(), mean_vhat=vhat.mean())


if __name__ == '__main__':
    verify()
    results = [
        run('base'),
        run('low_baseline', baseline=.1, mu=0, tau=.08),
        run('positive_seed_coupling', coupling='positive'),
        run('negative_seed_coupling', coupling='negative'),
        run('shared_sector', family=.12),
        run('fixed_mechanisms', baseline=.4, mu=0, tau=.0, mechanisms=(-.2,0,.2)),
        run('zero_heterogeneity', mu=0, tau=0),
    ]
    (HERE / 'prediction_results.json').write_text(json.dumps(results, indent=2))
    for r in results:
        print(r)
