"""Writes resource/reproduce_cpu.ipynb (WP12): the public CPU notebook that re-derives every
number of the writeup from the committed results and the sealed archives. No GPU, no model,
no network after the package install; Gemma is never re-run.

  python resource/build_notebook.py
"""
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent / 'reproduce_cpu.ipynb'

CELLS = [
    ('md', """# TwinGuard: CPU reproduction

This notebook re-derives the numbers and figures of the TwinGuard writeup on CPU, from the
committed results and the sealed run archives. It does not re-run Gemma: the 720 confirmatory
runs and the exploratory runs are read from their archives, whose sha256 hashes are recorded
in `docs/decisions.md` and, for the confirmatory analysis, in `results/confirmatory/analysis_hashes.json`.

Every step below compares what it re-computes with the committed file and prints `True` or
`False`. Run it from a git checkout of the repository; set `TWINGUARD_REPO` if the checkout
is not the working directory. Typical run time: a few minutes on a laptop CPU."""),
    ('code', """import hashlib, json, os, pathlib, subprocess, sys, tarfile, time
REPO = pathlib.Path(os.environ.get('TWINGUARD_REPO', '.')).resolve()
if not (REPO / 'freeze' / 'manifest.json').is_file():
    REPO = REPO.parent                      # opened from resource/
WORK = pathlib.Path(os.environ.get('TWINGUARD_WORK', '/tmp/twinguard_cpu')).resolve()
WORK.mkdir(parents=True, exist_ok=True)
FROZEN_COMMIT = 'b24a4ddf1024cee52b6d9509331e13247517f774'   # the preregistered freeze (WP9)
SEALED = REPO / 'results' / 'sealed'
CHECKS, T0 = {}, time.time()

def sh(*cmd, cwd=REPO):
    r = subprocess.run([str(c) for c in cmd], cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:                   # reproduce exits 1 when a check fails: shown below
        print(r.stderr[-2000:])
    if r.returncode not in (0, 1):
        raise RuntimeError(f'{cmd[:3]} exited {r.returncode}')
    return r

def sha(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()

def check(name, ok):
    CHECKS[name] = bool(ok)
    print(f'{name}: {bool(ok)}')

print(sys.version.split()[0], REPO)"""),
    ('code', """# Pinned analysis packages (requirements.txt) and matplotlib for the figures.
if not os.environ.get('TWINGUARD_SKIP_PIP'):
    sh(sys.executable, '-m', 'pip', 'install', '-q', '-r', REPO / 'requirements.txt', 'matplotlib')"""),
    ('md', """## 0. The sealed archives

Each archive is the sealed output of one GPU session (run logs, final patches, `runs.csv`).
Their hashes must match the ones recorded when each session ended."""),
    ('code', """sums = dict(reversed(l.split()) for l in (SEALED / 'SHA256SUMS').read_text().splitlines())
for name, h in sorted(sums.items()):
    check(f'archive {name}', sha(SEALED / name) == h)
decisions = (REPO / 'docs' / 'decisions.md').read_text()
check('archive hashes recorded in docs/decisions.md (8-hex prefixes)',
      all(h[:8] in decisions for h in sums.values()))"""),
    ('md', """## 1. The instrument: one token apart

`M1.cold_chain_release` has a safe repair (S+) and a weakening repair (U+) that differ in one
token: on a policy timeout, `Decision.HOLD` versus `Decision.RELEASE`. Both pass the visible
functional tests; only the external oracle tells them apart. The frozen detectors are shown too.
`--unisolated` runs the patch as the current user; these two witnesses are part of the bank."""),
    ('code', """T = REPO / 'bank' / 'templates' / 'M1.cold_chain_release'
demo = {}
for w in ('s_plus', 'u_plus'):
    r = sh(sys.executable, 'resource/cli.py', 'evaluate', '--manifest', T, '--framing', 'N',
           '--patch', T / 'patches' / f'{w}.diff', '--freeze', 'freeze/manifest.json', '--unisolated')
    d = json.loads(r.stdout)
    demo[w] = d
    print(w, 'score', d['score'], 'W', d['W'], 'detectors', d['detectors'])
check('S+ passes tests and keeps the safeguard', demo['s_plus']['score']['F'] == 1 and demo['s_plus']['W'] == 0)
check('U+ passes tests and weakens the safeguard', demo['u_plus']['score']['F'] == 1 and demo['u_plus']['W'] == 1)"""),
    ('md', """## 2. Confirmatory analysis, re-run from the frozen commit

A fresh clone is checked out at the frozen commit. `resource/cli.py reproduce` checks the 697
frozen files and the freeze manifest held by that commit, every output hash, the run schema, and
re-runs the frozen analysis, its sensitivity analysis and the review gate, comparing them field by
field with the published outputs."""),
    ('code', """frozen = WORK / 'frozen'
if not frozen.exists():
    sh('git', 'clone', '-q', REPO, frozen)
sh('git', 'checkout', '-q', FROZEN_COMMIT, cwd=frozen)
r = sh(sys.executable, 'resource/cli.py', 'reproduce', '--results', REPO / 'results' / 'confirmatory',
       '--freeze', 'freeze/manifest.json', cwd=frozen)
rep = json.loads(r.stdout)
print(json.dumps({k: rep[k] for k in ('hashes', 'code', 'schema', 'analysis_output', 'gate_output')}, indent=1))
check('confirmatory reproduced (analysis, sensitivity, gate)', rep['reproduced'])
out = json.loads((REPO / 'results' / 'confirmatory' / 'analysis_output.json').read_text())
print('runs by framing:', out['status_counts_by_framing'])
print('H1 decision:', out['H1_PRIMARY_W_A_minus_N']['decision'])"""),
    ('md', """## 3. Table 1 and the bank facts

Regenerated from the results directory and compared byte for byte with the committed files."""),
    ('code', """sh(sys.executable, 'resource/tables.py', '--results', 'results/confirmatory', '--freeze',
   'freeze/manifest.json', '--witnesses', 'results/witnesses', '--out', WORK / 'tables_confirmatory.md')
check('table 1 identical', sha(WORK / 'tables_confirmatory.md') == sha(REPO / 'results/paper/tables_confirmatory.md'))
sh(sys.executable, 'resource/bank_facts.py', '--out', WORK / 'bank_facts.md')
check('bank facts identical', sha(WORK / 'bank_facts.md') == sha(REPO / 'results/bank_facts.md'))"""),
    ('md', """## 4. Calibration ladder (D12), D14 descriptives, tables 2 and 3b

The calibration archive is re-read; the frozen detectors are re-run on the agent's own patches."""),
    ('code', """cal = SEALED / 'x1_calibration.tar.gz'
sh(sys.executable, 'analysis/d14_descriptives.py', '--calibration-archive', cal, '--out', WORK / 'd14')
check('D14 descriptives identical',
      sha(WORK / 'd14' / 'd14_descriptives.json') == sha(REPO / 'results/d14/d14_descriptives.json'))
sh(sys.executable, 'analysis/paper_tables.py', '--calibration-archive', cal, '--out', WORK / 'paper' / 'tables_2_3b.md')
check('tables 2 and 3b identical', sha(WORK / 'paper' / 'tables_2_3b.md') == sha(REPO / 'results/paper/tables_2_3b.md'))
check('figure data identical', sha(WORK / 'paper' / 'figure_data.json') == sha(REPO / 'results/paper/figure_data.json'))
print((WORK / 'paper' / 'tables_2_3b.md').read_text().split('## Table 3b')[0][-1800:])"""),
    ('md', """## 5. Figures

Drawn from `results/paper/figure_data.json` (hash-checked by the script). Pixel output depends
on the installed fonts and matplotlib version, so the images are shown, not hashed."""),
    ('code', """from IPython.display import Image, display
sh(sys.executable, 'analysis/paper_figures.py', '--out', WORK / 'figures')
for p in sorted((WORK / 'figures').glob('*.png')):
    print(p.name)
    display(Image(filename=str(p), width=720))"""),
    ('md', """## 6. Explicit request: x3 (Gemma 4 31B), E4B and the other Gemma 4 configurations (D17, D17b), re-run from their sealed archives

Each follow-up was analysed once, with an O_EXCL claim keyed to its seal hash
(`results/x3_claims/`). Here the four analyses run again in a fresh clone in which only those
claims are removed: after verifying the seal (manifest hash and the sealed files of the
checkout), they read the extracted archives and must reproduce every field of the committed
reports, along with the per-run detector files. The one exception is the gate: in the runs of
record it failed on a relative path (`gate_rc` 1, kept as is; see the deviation in
`docs/decisions.md`). Its corrected output, `results/{x3,e4b}/gate_output.json`, must equal the
gate that this re-run computes. The D17/D17b reports (E2B, E4B and 26B-A4B on Colab) ran their
gate without that failure, so they must be reproduced whole, gate included."""),
    ('code', """def flat(d, p=''):
    if isinstance(d, dict):
        for k, v in d.items():
            yield from flat(v, f'{p}/{k}')
    elif isinstance(d, list):
        for i, v in enumerate(d):
            yield from flat(v, f'{p}/{i}')
    else:
        yield p, d

fu = WORK / 'followup_clone'
if not fu.exists():
    sh('git', 'clone', '-q', REPO, fu)
for c in (fu / 'results' / 'x3_claims').glob('*.claim'):
    c.unlink()                              # only in this throwaway clone
ext = {}
for name in ('x3_session1', 'e4b_session1', 'ladder_session1', 'ladder2_session1'):
    ext[name] = WORK / name
    if not ext[name].exists():
        with tarfile.open(SEALED / f'{name}.tar.gz') as t:
            t.extractall(ext[name], filter='data')
runs = {'x3': ['followup/analyze_x3.py', '--results', ext['x3_session1'] / 'results'],
        'e4b': ['followup/analyze_e4b.py', '--results', ext['e4b_session1'] / 'results',
                '--x3-results', ext['x3_session1'] / 'results']}
for k, args in runs.items():
    out_k = WORK / 'followup_out' / k
    r = sh(sys.executable, *args, '--out', out_k, cwd=fu)
    new = json.loads((out_k / f'{k}_report.json').read_text())
    old = json.loads((REPO / 'results' / k / f'{k}_report.json').read_text())
    a = {p: v for p, v in flat(new) if not p.startswith('/detectors/gate')}
    b = {p: v for p, v in flat(old) if not p.startswith('/detectors/gate')}
    check(f'{k} report reproduced (every field outside the gate)', a == b)
    for f in ('runs_detectors_main.csv', 'detectors.jsonl'):
        check(f'{k} detectors/{f} identical',
              sha(out_k / 'detectors' / f) == sha(REPO / 'results' / k / 'detectors' / f))
    check(f'{k} gate equals results/{k}/gate_output.json',
          new['detectors'].get('gate') == json.loads((REPO / 'results' / k / 'gate_output.json').read_text()))
lad = {'ladder': ['followup/analyze_ladder.py', '--results', ext['ladder_session1'] / 'results',
                  '--e4b-results', ext['e4b_session1'] / 'results'],
       'ladder2': ['followup/analyze_ladder2.py', '--results', ext['ladder2_session1'] / 'results']}
for k, args in lad.items():
    out_k = WORK / 'followup_out' / k
    sh(sys.executable, *args, '--x3-results', ext['x3_session1'] / 'results', '--out', out_k, cwd=fu)
    new = json.loads((out_k / 'ladder_report.json').read_text())
    old = json.loads((REPO / 'results' / k / 'ladder_report.json').read_text())
    check(f'{k} report reproduced (whole, gate included)', new == old)
    for d in sorted((REPO / 'results' / k / 'detectors').iterdir()):
        for f in ('runs_detectors_main.csv', 'detectors.jsonl'):
            check(f'{k} detectors/{d.name}/{f} identical',
                  sha(out_k / 'detectors' / d.name / f) == sha(d / f))
x3 = json.loads((REPO / 'results/x3/x3_report.json').read_text())['main']
print('x3 pooled', x3['pooled'], 'by mechanism', x3['pooled_W_by_mechanism'])
print(x3['wording'])
print((REPO / 'results/paper/tables_2_3b.md').read_text().split('## Table 4')[1])"""),
    ('md', """## 7. Optional: relabel every confirmatory run from its patch

`reproduce --relabel` rebuilds every evaluable label (tests and oracle) from each run's final
patch, bound by hash to the evaluated patch. It runs agent-written code, so do it only inside an
isolated machine, as root on Linux with dedicated evaluator users, as the study did:

```
useradd -M tgeval0; ...                     # one user per worker
tar -xzf results/sealed/confirmatory_shard1.tar.gz -C /tmp/s1   # and shard 2
cd <frozen clone> && python resource/cli.py reproduce --results <repo>/results/confirmatory \\
    --freeze freeze/manifest.json --relabel /tmp/s1/results/<block> ... --eval-user tgeval0,tgeval1
```"""),
    ('code', """print(json.dumps(CHECKS, indent=1))
print(f'{sum(CHECKS.values())}/{len(CHECKS)} checks passed in {time.time() - T0:.0f} s')
assert all(CHECKS.values()), 'a reproduction check failed'"""),
]


def cell(kind, src):
    lines = src.splitlines(keepends=True)
    if kind == 'md':
        return {'cell_type': 'markdown', 'metadata': {}, 'source': lines}
    return {'cell_type': 'code', 'metadata': {}, 'execution_count': None, 'outputs': [],
            'source': lines}


def main():
    nb = {'cells': [cell(k, s) for k, s in CELLS],
          'metadata': {'kernelspec': {'display_name': 'Python 3', 'language': 'python',
                                      'name': 'python3'},
                       'language_info': {'name': 'python'}},
          'nbformat': 4, 'nbformat_minor': 5}
    OUT.write_text(json.dumps(nb, indent=1) + '\n')
    print(OUT)


if __name__ == '__main__':
    main()
