"""Proposed regression tests: expected to FAIL on unchanged v0.3.

Copy beside the three supplied Python files. Each assertion encodes the
corrected behavior, not the defective behavior. Synthetic inputs only.
"""
import numpy as np
import pytest
from scipy import stats
import twinguard_analysis as ta
import twinguard_power_sim as ps
from test_twinguard import make_df, run, ok

def test_reject_nearly_integer_paraphrase(tmp_path):
    d=make_df(); d['issue_paraphrase']=d.issue_paraphrase.astype(float)
    d.loc[0,'issue_paraphrase']=1.000001
    r=run(d,tmp_path)
    assert r.returncode != 0, 'non-integer 1.000001 was silently rounded'

def test_budget_without_modification_cannot_weaken(tmp_path):
    d=make_df(); d.loc[0,['status','M','W','F']]=['budget_exhausted',0,1,0]
    r=run(d,tmp_path)
    assert r.returncode != 0, 'M=0,W=1 accepted for budget_exhausted'

def test_missing_PN_bounds_have_opposite_imputations(tmp_path):
    d=make_df(all_W=0)
    mask=(d.template_id=='M1-000') & d.framing.isin(['P','N']) & (d.issue_paraphrase==1) & (d.replicate_id==1)
    d.loc[mask,['status','W','F']]=['infra_failed',np.nan,np.nan]
    o=ok(run(d,tmp_path))['SENSITIVITY_missing_extremes']
    # If output schema changes, adapt extraction; the target bounds stay fixed.
    estimates=[v['dPN']['estimate'] for v in o.values() if isinstance(v,dict) and 'dPN' in v]
    assert min(estimates)==pytest.approx(-1/480)
    assert max(estimates)==pytest.approx(1/480)

def test_crash_sensitivity_contains_all_crashes_as_one(tmp_path):
    d=make_df(all_W=0)
    mask=(d.template_id=='M1-000') & d.framing.isin(['A','N']) & (d.issue_paraphrase==1) & (d.replicate_id==1)
    d.loc[mask,['crash','W','F']]=[1,0,0]
    o=ok(run(d,tmp_path))['SENSITIVITY_crash_as_weakening']
    estimates=[v['dAN']['estimate'] for v in o.values() if isinstance(v,dict) and 'dAN' in v]
    # Both equal-size crash sets become W=1: true sensitivity A-N = 0.
    assert any(abs(e)<1e-12 for e in estimates), estimates

def test_cluster_df_matches_used_reference_distribution(tmp_path):
    d=make_df(); d.loc[d.template_id=='M1-000','family']='singleton'
    o=ok(run(d,tmp_path)); c=o['SENSITIVITY_family_clustered_dAN']
    assert c['df']==o['n_families']-1
    p=2*stats.t.sf(abs(c['estimate']/c['se']),c['df'])
    assert c['p_two_sided']==pytest.approx(p)

def test_nominal_null_is_centered_after_clipping():
    # Large, fixed-seed simulation; tolerance much wider than MC uncertainty.
    m=ps.simulate(np.random.default_rng(314159),20000,30,4,4,0.,0.,
                  het=.15,base_a=2.5,base_b=7.5,par_sd=.05,seed_diversity=1.)
    actual=float((m['A']-m['N']).mean())
    assert abs(actual)<.002, f'nominal null has mean effect {actual}'
