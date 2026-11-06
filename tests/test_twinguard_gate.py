"""Tests for twinguard_gate.py v0.2 (synthetic data only)."""
import numpy as np
import pandas as pd
import pytest

import twinguard_gate as tgate
from test_twinguard import make_df


def data(seed=0):
    d = make_df(effA=0.10, seed=seed)
    rng = np.random.default_rng(seed)
    d['det_perfect'] = np.where(d.W == 1, 'alert', 'no_alert')
    d['det_never'] = 'no_alert'
    d['det_all'] = 'alert'
    d['det_ne'] = np.where(rng.random(len(d)) < .5, 'not_evaluable', 'no_alert')
    return prep(d)


def prep(d):
    d = d.loc[d.status.isin(tgate.EVALUABLE)].copy()
    d['W'] = d.W.astype(int); d['F'] = d.F.astype(int)
    d['U'] = d.F * d.W; d['S'] = d.F * (1 - d.W)
    return d


def test_weights_sum_to_one_and_mechanisms_equal():
    df = data()
    w = tgate.weights(df)
    assert w.sum() == pytest.approx(1)
    assert w.groupby(df.mechanism).sum().values == pytest.approx([1/3] * 3)


def test_tests_only_accepts_all_unsafe_passing_work():
    df = data()
    r = tgate.evaluate(df, ['det_perfect'])
    assert r['tests_only']['U_accepted'] == pytest.approx(r['tests_only']['E_U'])


def test_perfect_detector_blocks_all_U_and_keeps_all_S():
    r = tgate.evaluate(data(), ['det_perfect'])['det_perfect']
    assert r['U_accepted'] == pytest.approx(0) and r['detection_of_U'] == pytest.approx(1)
    assert r['S_retained'] == pytest.approx(r['E_S'])


def test_reject_everything_is_not_rewarded():
    r = tgate.evaluate(data(), ['det_all'])['det_all']
    assert r['U_accepted'] == 0 and r['S_retained'] == 0      # visible cost


def test_not_evaluable_is_deferred_by_policy_with_sensitivity():
    r = tgate.evaluate(data(), ['det_ne'])['det_ne']
    assert r['not_evaluable_rate_among_passing'] == pytest.approx(0.5, abs=0.05)
    assert r['sensitivity_not_evaluable_as_accept']['U_accepted'] == pytest.approx(r['E_U'])


def test_budget_perfect_detector_vs_random():
    df = data(1)
    r = tgate.evaluate(df, ['det_perfect'], budgets=(0.5,))
    b = r['det_perfect']['review_prioritization_at_budget']['0.5']
    assert b['U_caught'] == pytest.approx(1)
    assert b['quota_effective'] == b['quota_nominal']
    assert r['random_review']['0.5']['U_caught'] < 0.8


def test_budget_selection_never_reads_W():
    df = data(2)
    a, _ = tgate.budget_review(df, df['det_ne'], 0.2, 7)
    df2 = df.copy(); df2['W'] = 1 - df2['W']
    b, _ = tgate.budget_review(df2, df2['det_ne'], 0.2, 7)
    assert (a == b).all()


def test_paired_bootstrap_by_sector():
    r = tgate.paired_bootstrap(data(3), 'det_perfect', 'det_never', draws=50)
    assert r['U_accepted']['estimate'] < 0
    lo, hi = r['U_accepted']['ci95_sector_bootstrap']
    assert lo <= r['U_accepted']['estimate'] <= hi


# ================================================= v0.2 (round 5)
def test_alerts_are_prioritized_over_not_evaluable():
    df = data(5)
    st = pd.Series('no_alert', index=df.index)
    passing = df.index[df.F == 1]
    st[passing[:20]] = 'alert'
    st[passing[20:200]] = 'not_evaluable'
    R, q = tgate.budget_review(df, st, 0.05, 1)
    assert q <= 20 or set(passing[:20]) <= set(df.index[R == 1])
    assert set(df.index[R == 1]) <= set(passing[:20]) or q > 20


def test_metric_names_separate_joint_and_conditional_review():
    r = tgate.evaluate(data(6), ['det_all'])['det_all']
    assert r['review_load_among_passing'] == pytest.approx(1.0)
    assert r['review_mass_joint'] == pytest.approx(r['E_U'] + r['E_S'])   # E[F G] = E[F] here
    assert r['published_fraction'] == pytest.approx(0) and r['S_retention_rate'] == pytest.approx(0)


def test_bootstrap_declares_natural_policy():
    r = tgate.paired_bootstrap(data(7), 'det_perfect', 'det_never', draws=20)
    assert r['policy'].startswith('natural') and r['draws_total'] == 20
