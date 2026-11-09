# Deviations after the freeze (protocol 9.4; CLAUDE.md rule 4)

Freeze: manifest of commit `8bceffe`, committed in `b24a4dd`, SHA-256 `e2a98129…`, stamped with
OpenTimestamps on 2026-11-09 ~09:43 Chile.

## DEV-1. Kernel bundle lacked `bank/spec_matrix.csv.sha256` (packaging tool; no run affected)

- **What happened.** The first launch of both confirmatory shards (`twinguard-conf-s{1,2}of2-k1`,
  2026-11-09 09:44 Chile) stopped at the start-up check `6_verify_freeze`:
  `bundle differs from the freeze: missing=['bank/spec_matrix.csv.sha256']`. The kernel
  refused to run, as designed. No model call and no run took place.
- **Cause.** The frozen kernel checks every manifest file under its `BUNDLED` prefixes;
  the prefix `bank/spec_matrix.csv` also matches `bank/spec_matrix.csv.sha256`, which the
  manifest lists. The local packaging tool `notebooks/build_kernel.py` archived only
  `bank/spec_matrix.csv`. The dry run before the freeze did not exercise this check against a
  real bundle.
- **Fix.** `notebooks/build_kernel.py` (a launcher run on the author's machine, never inside
  the kernel) now also archives `bank/spec_matrix.csv.sha256`. The bundle is still
  `git archive` of the frozen commit, and the kernel script is still the frozen one, so every
  file the kernel runs and checks has its frozen hash. Regression test:
  `tests/test_bundle_freeze.py` rebuilds the archive from the frozen commit and applies the
  frozen kernel's check (no missing, no different and no extra file; 672 files checked).
- **Effect on the study.** None on the design, the bank, the code that runs, the seeds or the
  schedule. The confirmatory shards are relaunched as kernel version 2 of the same kernels.
  Quota used by the failed start: about 2 minutes per shard.
