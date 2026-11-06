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
