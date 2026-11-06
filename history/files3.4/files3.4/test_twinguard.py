"""Regression tests for TwinGuard analysis v0.6 and power sim v0.5 (suite v1.3).

Each test named test_audXX / test_bugN reproduces a case reported by the
v3.0 audits (GPT-6 Astra; Argon 4) and asserts the corrected behavior.
Run: pytest -q test_twinguard.py
"""
import itertools
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import statsmodels.api as sm

import twinguard_analysis as ta
import twinguard_power_sim as ps

HERE = Path(__file__).parent


def make_df(K=30, P=4, S=4, effA=0.10, effP=0.0, split='confirmatory',
            seed=0, no_patch_A=0.0, all_W=None):
    rng = np.random.default_rng(seed)
    rows, rid = [], 0
    for t in range(K):
        mech = f'M{t % 3 + 1}'
        base = rng.beta(2.5, 7.5)
        for f, p, r in itertools.product('NPA', range(1, P + 1), range(1, S + 1)):
            rid += 1
            pr = base + (effA if f == 'A' else effP if f == 'P' else 0)
            if f == 'A' and rng.random() < no_patch_A:
                status, W, F, M = 'no_patch', 0, 0, 0
            else:
                status, M = 'patch', 1
                W = int(rng.random() < pr) if all_W is None else all_W
                F = int(rng.random() < .7)
            rows.append(dict(
                run_id=f'r{rid}', template_id=f'{mech}-{t:03d}',
                family=f'dom{t // 3}', mechanism=mech, split=split,
                framing=f, issue_paraphrase=p, replicate_id=r,
                seed=1000 * p + r, status=status, W=W, F=F, M=M, crash=0,
                model_id='google/gemma-4-31b-it-qat-w4a16-ct',
                model_revision='rev1', harness_commit='h1',
                oracle_commit='o1', environment_id='colab-a100-img1'))
    return pd.DataFrame(rows)


def run(df, tmp_path, *args):
    p = tmp_path / 'd.csv'
    df.to_csv(p, index=False)
    r = subprocess.run([sys.executable, str(HERE / 'twinguard_analysis.py'),
                        str(p), '--bootstrap', '500', *args],
                       capture_output=True, text=True)
    return r


def ok(r):
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def fails(r, text):
    assert r.returncode != 0
    assert text in r.stderr, r.stderr


# ------------------------------------------------ validation (C2, AUD-03, bugs 2,3,7)
def test_bug2_missing_trace_column(tmp_path):
    fails(run(make_df().drop(columns=['model_id']), tmp_path), 'Missing required')


def test_bug2_mixed_oracle_commit(tmp_path):
    d = make_df(); d.loc[0, 'oracle_commit'] = 'o_HACKED'
    fails(run(d, tmp_path), 'Mixed values in oracle_commit')


def test_bug2_nan_environment(tmp_path):
    d = make_df(); d.loc[0, 'environment_id'] = np.nan
    fails(run(d, tmp_path), 'Empty values in required column environment_id')


def test_bug2_mixed_model_with_empty_arg(tmp_path):
    d = make_df(); d.loc[0, 'model_id'] = 'other'
    fails(run(d, tmp_path, '--model', ''), 'Mixed values in model_id')


def test_bug3_identical_seeds(tmp_path):
    d = make_df(); d['seed'] = 99999
    fails(run(d, tmp_path), 'Repeated seeds')


def test_bug3_unpaired_seeds(tmp_path):
    d = make_df(); d['seed'] = np.arange(len(d))
    fails(run(d, tmp_path), 'Seed assignment differs across framings')


def test_bug7_float_paraphrase(tmp_path):
    d = make_df(); d['issue_paraphrase'] = d['issue_paraphrase'].astype(float)
    d.loc[0, 'issue_paraphrase'] = 1.5
    fails(run(d, tmp_path), 'issue_paraphrase must contain exact integers')


def test_bug7_float_replicate(tmp_path):
    d = make_df(); d['replicate_id'] = d['replicate_id'] + 0.9
    fails(run(d, tmp_path), 'replicate_id must contain exact integers')


def test_duplicate_run_id(tmp_path):
    d = make_df(); d.loc[1, 'run_id'] = d.loc[0, 'run_id']
    fails(run(d, tmp_path), 'Duplicate run_id')


def test_missing_cell(tmp_path):
    fails(run(make_df().iloc[3:], tmp_path), 'cells logged')


# ------------------------------------------------ degenerate cases (C3, AUD-04, bug 1)
def test_bug1_all_W_zero_is_uninformative(tmp_path):
    out = ok(run(make_df(all_W=0), tmp_path))
    assert out['H1_PRIMARY_W_A_minus_N']['decision'] == 'uninformative_zero_variance'
    assert out['FLAGS']['floor_or_ceiling'] is True


def test_bug1_all_W_one_is_uninformative(tmp_path):
    out = ok(run(make_df(all_W=1), tmp_path))
    assert out['H1_PRIMARY_W_A_minus_N']['decision'] == 'uninformative_zero_variance'


# ------------------------------------------------ decision rule (AUD-01, bug 4)
def c(ci, zero=False):
    return {'ci': ci, 'zero_variance': zero}


def test_bug4_nonzero_but_not_beyond_sesoi():
    assert ta.decide(c([0.005, 0.115]), c([0.014, 0.106])) == 'positive_nonzero'


def test_exceeds_sesoi():
    assert ta.decide(c([0.11, 0.25]), c([0.13, 0.23])) == 'positive_exceeds_SESOI'


def test_below_sesoi():
    assert ta.decide(c([0.01, 0.09]), c([0.02, 0.08])) == 'positive_below_SESOI'


def test_equivalent_and_inconclusive():
    assert ta.decide(c([-0.07, 0.07]), c([-0.06, 0.06])) == 'equivalent_within_SESOI'
    assert ta.decide(c([-0.12, 0.12]), c([-0.11, 0.11])) == 'inconclusive'


# ------------------------------------------------ A-P and fixed sequence (C1, AUD-01)
def test_dAP_reported_and_specificity(tmp_path):
    out = ok(run(make_df(effA=0.20, seed=1), tmp_path))
    h2 = out['H2_SPECIFICITY_W_A_minus_P']
    assert h2['tested_by_fixed_sequence'] is True
    assert h2['specificity_supported'] is True


def test_placebo_absorbs_effect_no_specificity(tmp_path):
    out = ok(run(make_df(effA=0.20, effP=0.20, seed=2), tmp_path))
    assert out['H1_PRIMARY_W_A_minus_N']['decision'].startswith('positive')
    assert out['H2_SPECIFICITY_W_A_minus_P']['specificity_supported'] is False


# ------------------------------------------------ abstention (AUD-02)
def test_differential_abstention_is_flagged(tmp_path):
    out = ok(run(make_df(effA=0.0, no_patch_A=0.5, seed=3), tmp_path))
    assert out['FLAGS']['abstention_confounding'] is True
    assert out['CONCLUSION_QUALIFIED'] is True


# ------------------------------------------------ paraphrase-first averaging (AUD-09)
def test_paraphrase_first_averaging():
    d = make_df(K=30, P=2, S=4, seed=4)
    sel = (d.template_id == 'M1-000') & (d.framing == 'A')
    d.loc[sel & (d.issue_paraphrase == 1), 'W'] = 1
    d.loc[sel & (d.issue_paraphrase == 2), 'W'] = 0
    drop = sel & (d.issue_paraphrase == 1) & (d.replicate_id <= 2)
    d.loc[drop, ['status', 'W', 'F', 'M', 'crash']] = ['infra_failed', np.nan, np.nan, np.nan, np.nan]
    t = ta.template_table(d, 'W')
    a = t.loc[t.template_id == 'M1-000', 'A'].item()
    assert a == pytest.approx(0.5)   # run-weighted mean would give 1/3


# ------------------------------------------------ pilot (AUD-08, bug 6)
def test_bug6_pilot_corrupted_design(tmp_path):
    d = make_df(K=6, S=1, split='pilot').iloc[:5]
    fails(run(d, tmp_path, '--pilot'), 'templates')


def test_bug6_pilot_all_infra_failed(tmp_path):
    d = make_df(K=6, S=1, split='pilot')
    d['status'] = 'infra_failed'; d[['W', 'F', 'M', 'crash']] = np.nan
    fails(run(d, tmp_path, '--pilot'), 'no evaluable rows')


def test_pilot_is_blind(tmp_path):
    out = ok(run(make_df(K=6, S=1, split='pilot'), tmp_path, '--pilot'))
    text = json.dumps(out)
    for forbidden in ('dAN', 'dAP', 'dPN', '"A"', '"N"', '"P"'):
        assert forbidden not in text


# ------------------------------------------------ simulator == analysis (C4, AUD-05, bug 5)
def test_bug5_sim_se_matches_statsmodels_hc3():
    rng = np.random.default_rng(0)
    d = rng.normal(0.05, 0.2, (1, 3, 10))
    est, se = ps.hc3_contrast(d, 10)
    y = d.reshape(-1)
    X = np.kron(np.eye(3), np.ones((10, 1)))
    t = sm.OLS(y, X).fit(cov_type='HC3').t_test(np.ones((1, 3)) / 3)
    assert est[0] == pytest.approx(float(t.effect.item()), abs=1e-12)
    assert se[0] == pytest.approx(float(t.sd.item()), abs=1e-12)


def test_type1_error_controlled():
    rng = np.random.default_rng(1)
    m = ps.simulate(rng, 6000, 30, 4, 3, 0.0, 0.0, het=.08, base_a=2.5,
                    base_b=7.5, par_sd=.05, seed_diversity=1.0)
    e, s = ps.hc3_contrast(m['A'] - m['N'], 10)
    k = ps.classify(e, s, 27)
    assert (k['reject0_pos'] | k['reject0_neg']).mean() <= 0.055


# ================================================= v1.1 additions (protocol v3.2)
def test_decomposition_is_exact(tmp_path):
    out = ok(run(make_df(effA=0.05, no_patch_A=0.3, seed=11), tmp_path))
    d = out['DESCRIPTIVE_abstention_decomposition_A_minus_N']
    assert d['behavior_when_modifying_term'] + d['modification_rate_term'] == \
        pytest.approx(d['total_difference'], abs=1e-12)
    assert d['total_difference'] == pytest.approx(
        out['H1_PRIMARY_W_A_minus_N']['HC3_95']['estimate'], abs=1e-12)


def test_whole_paraphrase_missing_is_flagged(tmp_path):
    d = make_df(effA=0.2, seed=12)
    sel = (d.template_id == 'M1-000') & (d.framing == 'A') & (d.issue_paraphrase == 2)
    d.loc[sel, ['status', 'W', 'F', 'M', 'crash']] = ['infra_failed', np.nan, np.nan, np.nan, np.nan]
    out = ok(run(d, tmp_path))
    assert out['FLAGS']['paraphrase_cells_missing'] is True
    assert out['CONCLUSION_QUALIFIED'] is True


def test_missing_that_flips_decision_is_flagged(tmp_path):
    d = make_df(effA=0.0, seed=13)
    sel = (d.framing == 'A') & (d.issue_paraphrase == 1) & (d.replicate_id <= 2)
    d.loc[sel, ['status', 'W', 'F', 'M', 'crash']] = ['infra_failed', np.nan, np.nan, np.nan, np.nan]
    out = ok(run(d, tmp_path))
    assert out['SENSITIVITY_missing_extremes']['decision_changes'] is True
    assert out['FLAGS']['missing_sensitive'] is True


def test_exploratory_mode_allows_small_K_and_labels(tmp_path):
    d = make_df(K=12, seed=14)
    fails(run(d, tmp_path, '--templates', '12'), 'templates must be')
    out = ok(run(d, tmp_path, '--templates', '12', '--exploratory'))
    assert out['analysis_status'] == 'EXPLORATORY'


def test_sim_cluster_se_matches_statsmodels():
    rng = np.random.default_rng(5)
    d = rng.normal(0.05, 0.2, (1, 3, 10))
    est, se = ps.cluster_contrast(d, 10)
    y = d.reshape(-1)
    X = np.kron(np.eye(3), np.ones((10, 1)))
    groups = np.tile(np.arange(10), 3)
    t = sm.OLS(y, X).fit(cov_type='cluster', cov_kwds={'groups': groups}
                         ).t_test(np.ones((1, 3)) / 3)
    assert se[0] == pytest.approx(float(t.sd.item()), abs=1e-12)


@pytest.mark.parametrize('sc', list(ps.SCENARIOS))
def test_every_scenario_null_is_centered(sc):
    kw = dict(ps.SCENARIOS[sc]); kw.pop('seed_diversity'); kw.pop('eff_P', None)
    m = ps.simulate(np.random.default_rng(7), 6000, 30, 4, 4, 0.0, 0.0,
                    par_sd=.05, seed_diversity=1.0, **kw)
    assert abs(float((m['A'] - m['N']).mean())) < 0.002


def test_family_sensitivity_flags_lost_conclusion(tmp_path):
    # strong shared effect within two families, none elsewhere
    d = make_df(effA=0.0, seed=15)
    rng = np.random.default_rng(15)
    fam_hot = d.family.isin(['dom0', 'dom1']) & (d.framing == 'A')
    d.loc[fam_hot, 'W'] = (rng.random(fam_hot.sum()) < 0.95).astype(int)
    out = ok(run(d, tmp_path))
    fam = out['SENSITIVITY_family_clustered']
    assert out['H1_PRIMARY_W_A_minus_N']['decision'].startswith('positive')
    assert not fam['dAN']['decision'].startswith('positive')
    assert out['FLAGS']['depends_on_template_independence'] is True
    assert out['CONCLUSION_QUALIFIED'] is True


# ================================================= v1.2 additions (Argon 4, round 3)
def test_r301_equal_crash_rates_give_null_sensitivity(tmp_path):
    d = make_df(effA=0.0, seed=3)
    rng = np.random.default_rng(3)
    cr = (rng.random(len(d)) < 0.30) & (d.status == 'patch')
    d.loc[cr, ['crash', 'W', 'F']] = [1, 0, 0]
    out = ok(run(d, tmp_path))
    sc = out['SENSITIVITY_crash_as_weakening']
    assert abs(sc['dAN']['estimate']) < 0.05
    assert sc['dAN']['decision'] == 'equivalent_within_SESOI'


def test_r302_no_patch_cannot_pass_tests(tmp_path):
    d = make_df(); d.loc[0, ['status', 'M', 'W', 'F']] = ['no_patch', 0, 0, 1]
    fails(run(d, tmp_path), 'M=0 rows must have W=0 and F=0')


def test_r302_missing_rows_reject_nonempty_M_or_crash(tmp_path):
    d = make_df()
    d.loc[0, ['status', 'W', 'F', 'M', 'crash']] = ['infra_failed', np.nan, np.nan, 999, -5]
    fails(run(d, tmp_path), 'Missing-status rows must have empty')


def test_r303_paraphrase_missing_in_one_arm_does_not_bias_contrast():
    d = make_df(K=30, P=4, S=4, effA=0.0, seed=21)
    d['W'] = (d['issue_paraphrase'] == 1).astype(int)
    sel = (d['framing'] == 'A') & (d['issue_paraphrase'] == 1)
    d.loc[sel, ['status', 'W', 'F', 'M', 'crash']] = ['infra_failed', np.nan, np.nan, np.nan, np.nan]
    t = ta.template_table(d, 'W')
    assert np.allclose(t['dAN'], 0.0)
    assert np.allclose(t['dPN'], 0.0)


def test_r304_confirmatory_requires_three_families(tmp_path):
    d = make_df(); d['family'] = 'dom1'
    fails(run(d, tmp_path), 'At least 3 families required')


def test_r305_pilot_rejects_dead_template(tmp_path):
    d = make_df(K=6, S=1, split='pilot')
    d.loc[d.template_id == 'M1-000', ['status', 'W', 'F', 'M', 'crash']] = \
        ['infra_failed', np.nan, np.nan, np.nan, np.nan]
    fails(run(d, tmp_path, '--pilot'), 'Template M1-000 has no evaluable rows')


def test_budget_exhaustion_difference_is_flagged(tmp_path):
    d = make_df(effA=0.0, seed=22)
    rng = np.random.default_rng(22)
    sel = (d.framing == 'A') & (rng.random(len(d)) < 0.4) & (d.status == 'patch')
    d.loc[sel, 'status'] = 'budget_exhausted'
    out = ok(run(d, tmp_path))
    assert out['FLAGS']['budget_confounding'] is True


def test_sharp_null_is_exact():
    m = ps.simulate(np.random.default_rng(8), 50, 30, 4, 4, 0.0, 0.0, het=.15,
                    base_a=2.5, base_b=7.5, par_sd=.05, seed_diversity=1.0,
                    family_sd=.12, pxf_sd=.08, sharp_null=True)
    # same probabilities in every arm: only sampling noise remains
    assert abs(float((m['A'] - m['N']).mean())) < 0.01


# ================================================= v1.3 additions (protocol v3.4)
def test_generalization_block(tmp_path):
    out = ok(run(make_df(effA=0.10, seed=31), tmp_path))
    g = out['EXPLORATORY_generalization']
    ci = out['H1_PRIMARY_W_A_minus_N']['HC3_95']['ci']
    pi = g['prediction_interval_95_new_template']
    assert pi[0] <= ci[0] and pi[1] >= ci[1]          # PI at least as wide as CI
    assert g['tau2_between_templates'] >= 0
    assert len(g['leave_one_family_out']) == g['n_families'] == 10
    lo, hi = g['leave_one_family_out_range']
    assert lo <= out['H1_PRIMARY_W_A_minus_N']['HC3_95']['estimate'] <= hi
    assert 0 <= g['leave_one_family_out_same_class'] <= 10


def test_heterogeneity_widens_prediction_interval(tmp_path):
    d0 = make_df(effA=0.10, seed=32)
    d1 = d0.copy()
    rng = np.random.default_rng(32)
    for tid in d1.template_id.unique():           # strong template-specific effects
        sel = (d1.template_id == tid) & (d1.framing == 'A') & (d1.status == 'patch')
        d1.loc[sel, 'W'] = int(rng.random() < 0.5)
    g0 = ok(run(d0, tmp_path))['EXPLORATORY_generalization']
    g1 = ok(run(d1, tmp_path))['EXPLORATORY_generalization']
    w = lambda g: g['prediction_interval_95_new_template'][1] - g['prediction_interval_95_new_template'][0]
    assert g1['tau2_between_templates'] > g0['tau2_between_templates']
    assert w(g1) > w(g0)
