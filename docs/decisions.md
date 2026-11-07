# Decision log

Dated decisions taken before the freeze. Each entry says who decided and what evidence it rests on.
Changes to the immutable core (CLAUDE.md §2) never go here without being a registered deviation.

## 2026-11-06

### D1. Friday 23:59 gate — operational interpretation (author, with Astra's wording)
For the Friday operational gate ("< 2 admitted templates per mechanism → prepare resource mode") the six
**pilot** templates with WP5 (technical) and WP6 (level-2 semantic audit) passed are counted; their
definitive admission remains pending WP7 and the resolution of validation defects. This interpretation
does not change the freeze criteria nor the requirement of 30 confirmatory templates; pilot templates never
count toward the 10 confirmatory per mechanism. Resource mode (§15.3) is prepared in parallel anyway.
Source: docs/advice/2026-11-06_astra_day1_review.md §3.

### D2. Verifier hardening after Astra's review (agent; stricter only)
Astra found that 3 of 6 pilot templates started with W=1 (initial state already violating the safeguard),
contradicting §8.3 (M=0 ⇒ W=0 because unmodified code preserves the safeguard). The verifier now requires
the initial state to run with every invariant holding, strict oracle output, declared check names, a crash
mutant, and other checks (commit c2bb3ad). The M2/M3 generation contracts in bank/sectors.toml were
amended so the initial state preserves the safeguard; the M3 router bug is functional (e.g. the pipeline
crashes on a non-critical report) while critical alerts already reach the audit sink. All six pilot
templates were rejected/superseded (bank/rejections.jsonl) and regenerated. No admission criterion was
relaxed.

### D2b. Verifier round 2 after Astra's second review (agent; stricter only)
Commit 51f45de: crash mutant restricted to the declared monitor functions; M1 abort must read as
crash=false and W=0; every template ships `patches/canary_break.diff` and a canary check must flip;
duplicate JSON keys rejected; README must carry the actor. Astra: the M2/M3 contract amendment is an
implementation clarification before the freeze (dated, with commit and regeneration), not a change of
manipulation or estimand. All six pilots regenerated again with the final prompt.

### D3. Pending author decisions (proposed, with Astra's agreement)
- **Chat template overlay:** serve Kaggle Models weights (byte-identical to HF 52f3f65) with HF 52f3f65's
  `chat_template.jinja` and `tokenizer_config.json` (Kaggle ships the release revision ca9d525 for them).
- **Harness:** keep the API-compatible replica (official swegemma is installable from the wheelhouse but its
  session input cannot carry the M3 conversation history without changing the M3 manipulation); align
  errors/serialization/messages with the real wheels via differential contract tests.
- **Graph tools:** static graph built once per template × framing at run start (as the official harness),
  instead of rebuilt after edits — needs an explicit amendment of §7.1 before the pilot.
- **Isolation:** run the agent's commands as a separate unprivileged user; oracles, logs and other runs
  unreadable to it (Astra: running in another directory is not isolation).
  Kaggle probe (CPU kernel `twinguard-isolation-probe`, pinned image, 2026-11-06): kernel runs as root;
  no bubblewrap; `unshare` (user/net/pid namespaces) not permitted; `useradd` + `setpriv --reuid
  --regid --clear-groups --no-new-privs` works (NoNewPrivs=1) and 0700 directories are denied.
  Localhost TCP is reachable by that user (vLLM port too) — try iptables owner-match; otherwise
  declare. Plan for the runner (WP8): agent tools + git + tests as uid `tgagent` under setpriv; oracles,
  templates, logs, other runs in 0700 controller dirs; `pkill -KILL -u tgagent` after each run;
  oracle evaluation on a clean patched copy as a second unprivileged uid; verify denial before pilot.

## 2026-11-07

### D4. Pre-pilot state (agent)
- Bank: 6 pilot + 30 confirmatory templates pass WP5 (final verifier), WP6 (GPT-6.1 Sol) and WP7
  (Gemma 31B, kernel twinguard-wp7-l4 v2, code b335552). Each has 4 issue paraphrases, validated
  automatically and judged equivalent by GPT-6.1 Sol (two templates' paraphrases regenerated).
- Runner (runner/runner.py) reviewed by Astra; all "imprescindible" items addressed (c69a25d).
  Runner smoke v3 on Kaggle (toy fixture, 6 runs, concurrency 3): all evaluated, ~100 s/run.
- Isolation verified on Kaggle: agent uids cannot read oracles, bank, results, harness code or
  other runs. **Residual, to declare:** `/kaggle/src/script.py` is read-only and world-readable
  (the shipped script carries no docstrings/comments; the code bundle is base64 gzip), and the
  vLLM port is reachable by the agent uid (no iptables, no network namespaces).
- Pending author decisions before the pilot: D3 items (template overlay, replica harness, graph
  updated after edits as in §7.1, isolation as implemented) and the go-ahead for the 72-run pilot
  (default budget: 100 tool calls, 60 min, reasoning on, concurrency 8).

### D5. Isolation and runner after Astra's second review (agent; stricter only)
Astra (2026-11-07, docs/advice) found that D4's residual risks were not residual: the
world-readable `/kaggle/src/script.py` carries the whole code bundle (37 oracles, solutions,
all framings) in reversible base64, and the evaluator uid owned the bank. Commit a51a561:
- `/kaggle` is chmod 0700 by root before any agent process exists: kernel source, inputs and
  working dir are denied to agent/evaluator uids (CPU probe `twinguard-isolation-probe2`,
  pinned image: all four denied; python/pytest still usable by the agent).
- vLLM listens only on a Unix socket in `/root/tgv` (0700); no TCP. An API key was rejected:
  vLLM 0.19.1 checks it only on `/v1` routes, `/invocations` stays open.
- The kernel aborts unless every denial check passes (sources, inputs, working dir, oracles,
  bank, harness, socket dir; the socket and TCP 8000 after the server starts).
- Agent file tools and graph source reads run as the agent uid (no controller reads on the
  agent's behalf). One evaluator uid per slot; evaluation on a private copy of the oracle;
  the bank is root-only; evaluator processes killed after each evaluation.
- Runner arguments travel in a root-only @file (the process list is visible to all uids).
- Resume never re-runs a finished episode; oracle errors go to blind adjudication
  (`runner/adjudicate.py`); `--stop-at` keeps every run inside the 12 h session.
- Pilot blinding: the kernel runs `twinguard_analysis.py --pilot` and writes a framing-free
  CSV; raw results (framings, logs) are sealed in `results_sealed.tar.gz` whose SHA-256 is
  reported, and are not opened before the authorized decoding except to debug a failure,
  with the reason logged.
Remaining, declared: `ps` shows command lines of all processes (the vLLM model path and the
runner path, no study terms); engine-internal local sockets of vLLM workers.
