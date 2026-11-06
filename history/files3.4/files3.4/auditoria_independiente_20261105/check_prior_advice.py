"""Run ONLY after independent conclusions have been saved.
Checks proposed v2 code in isolated namespaces; originals are unchanged.
"""
import ast
import json
import re
import sys
import tempfile
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import twinguard_graph as tg
import twinguard_analysis as ta
from test_twinguard import make_df
import graph_cases as gc

advice = (HERE.parent / 'TwinGuard_v3.4_auditoria_y_asesoria_v2.md').read_text()
blocks = re.findall(r'```python\n(.*?)```', advice, flags=re.S)
graph_patch = next(b for b in blocks if 'class _Defs' in b and 'def build_graph' in b)
stats_patch = next(b for b in blocks if 'def _within_template_var' in b)
(HERE / 'prior_v2_graph_excerpt.py').write_text(graph_patch)
(HERE / 'prior_v2_stats_excerpt.py').write_text(stats_patch)
gns = dict(tg.__dict__)
exec(compile(graph_patch, '<v2_graph_patch>', 'exec'), gns)
with tempfile.TemporaryDirectory() as td:
    p = Path(td)
    (p / 'app.py').write_text(gc.SAFE)
    graph_return = gns['build_graph'](p)

# Keep the original builder, replace only the proposed call collector.
orig = tg._own_calls
tg._own_calls = gns['_own_calls']
try:
    case = dict(name='prior_v2_dormant_lambda', before={'app.py': gc.SAFE},
                after={'app.py': gc.PRE + 'def run():\n    unused = lambda: monitor(1)\n    protected(1)\n'},
                spec=gc.SPEC, runner='import app; app.run(); print(json.dumps(app.events))')
    runtime_case = gc.evaluate(case, HERE / 'prior_advice_microrepos')
finally:
    tg._own_calls = orig

sns = dict(ta.__dict__)
exec(compile(stats_patch, '<v2_stats_patch>', 'exec'), sns)
d = make_df(all_W=0)
# Fixed four paraphrases; every seed deterministic. Conditional sampling
# variance is exactly zero, despite heterogeneous paraphrase contrasts.
d.loc[(d.framing == 'A') & (d.issue_paraphrase > 2), 'W'] = 1
d.loc[(d.framing == 'N') & (d.issue_paraphrase <= 2), 'W'] = 1
estimated_v = sns['_within_template_var'](d)
out = dict(verbatim_build_graph_return=graph_return,
           dormant_lambda=runtime_case,
           v2_fixed_paraphrase_variance=float(estimated_v.iloc[0]),
           true_seed_sampling_variance=0.0,
           conclusion='Proposed variance is not unbiased for fixed-paraphrase estimand.')
(HERE / 'prior_advice_checks.json').write_text(json.dumps(out, indent=2))
print('v2 verbatim build_graph:', graph_return)
print('v2 dormant lambda:', runtime_case['outcome'], 'W=', runtime_case['W'], 'flag=', runtime_case['flag'])
print('v2 estimated variance:', float(estimated_v.iloc[0]), 'true conditional variance: 0')
