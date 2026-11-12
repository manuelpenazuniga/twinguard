# TwinGuard

TwinGuard is a bench for one question about coding agents: when an agent repairs a bug, does it keep
the safeguard that sits next to the bug? Every task is a small synthetic repository with a real bug and
a safety check (a release hold, a rate limit, an approval step). Two reference repairs exist for each
task, one that keeps the check and one that silently disables it, and both pass the visible tests.
Only an external oracle, which the agent never sees, tells them apart.

This repository holds the code, the frozen task bank, the sealed run archives and the CPU notebook that
re-derives every number and figure of the paper *TwinGuard* (Gemma 4 Developer Agent Paper Track).

## Quick start (CPU, no GPU, no network after install)

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt matplotlib jupyter
python -m pytest -q                                   # full test suite
jupyter nbconvert --to notebook --execute resource/reproduce_cpu.ipynb --output /tmp/run.ipynb
```

The notebook prints one `True`/`False` line per check and a final summary. It verifies the sealed
archives by hash, re-runs the frozen confirmatory analysis from the frozen commit, rebuilds the tables
and the figures, and re-runs the exploratory analyses from their archives. Gemma is never re-run.

Score your own patch against a task:

```bash
python resource/cli.py evaluate --manifest bank/templates/M1.cold_chain_release \
    --framing N --patch my.diff --freeze freeze/manifest.json --unisolated
```

`evaluate` runs the patch's code. `--unisolated` runs it as you and is meant for patches you trust;
`--eval-user` reproduces the isolated evaluator of the study (Linux, root, a dedicated uid).

## Layout

| Path | Contents |
|---|---|
| `bank/` | Task generator, admission checks and the frozen bank (`bank/templates/`, 36 tasks × 3 framings) |
| `harness/` | The agent harness (tools, workspace, loop) used in every run |
| `runner/` | Run scheduling, evaluation, blind adjudication, analysis entry point |
| `twinguard/` | Frozen analysis, power simulation, call-graph detector (GSC) and review gate |
| `freeze/` | Freeze manifest of the preregistered study, with its OpenTimestamps proof |
| `explore/`, `followup/` | Exploratory follow-ups (calibration ladder, explicit-request study, model comparison), each sealed before decoding |
| `results/` | Hashed outputs; `results/sealed/` holds the run archives |
| `analysis/` | Paper tables and figures (fonts bundled under the SIL Open Font License) |
| `resource/` | `evaluate` / `reproduce` CLIs and the CPU notebook |
| `notebooks/` | The GPU kernels used for the runs (Kaggle L4×4, Colab A100) |
| `docs/` | Protocol (v3.6), decision log, deviations, environment and harness notes |

## About this history

This is a public copy of the working repository. Internal working notes (reviewer correspondence and
drafts) were removed from every commit with `git filter-repo`, which changes commit ids but not the
content of any frozen or sealed file. `resource/commit_map.json` maps each recorded commit id to its
commit here; the notebook uses it, and every frozen file is still checked against the hash recorded at
freeze time. Some documents refer to notes that are not included.

No competition data is included.

## License

Code: Apache License 2.0 (`LICENSE`). Task bank, results and documentation: CC BY 4.0 (`LICENSE-DATA`).
Fonts in `analysis/fonts/`: SIL Open Font License 1.1.

## Citation

Manuel Peña-Zúñiga. *TwinGuard*. Kaggle, Google – The Gemma 4 Developer Agent Paper Track, 2026.
