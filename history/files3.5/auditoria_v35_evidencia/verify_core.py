"""Synthetic invariance check; no changes to original analysis code."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import twinguard_analysis as analysis
from test_twinguard import make_df

d = make_df(seed=41)
args = SimpleNamespace(templates=30, paraphrases=4, replicates=4,
                       exploratory=False, bootstrap=20, seed=20261105)
before = analysis.confirmatory_report(d, args)
after = analysis.confirmatory_report(d.assign(gsc='no_alert'), args)
keys = ('H1_PRIMARY_W_A_minus_N', 'H2_SPECIFICITY_W_A_minus_P',
        'FLAGS', 'SENSITIVITY_family_clustered')
result = {key: before[key] == after[key] for key in keys}
assert all(result.values()), result
(HERE / 'core_invariance.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
