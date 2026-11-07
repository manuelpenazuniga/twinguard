# TwinGuard harness (WP2) — contract and declared differences

`harness/` is **API-compatible** with the official competition harness (`swegemma` +
`adk-eval-core`), replicated from the competition's `HARNESS_README.md` (sections 4–8,
read 2026-11-06). Neither package is on PyPI, but both ship as wheels in the official
dataset `metric/gemma-4-developer-agent-wheelhouse` and are installable on Kaggle L4x4.
**Why the replica is still used (proposed, pending author decision D3):** the official
session input carries only `problem_description` and `hints`, so the M3 conversation
history (protocol §5.2) cannot be given as history without changing the M3 manipulation.
The wheels carry no license and their code is not copied into this repo; it was read to
align errors, serialization and messages (pending: differential contract tests against the
wheels). Neither the README nor the wheels are copied here.

## Replicated as documented
- Tool names, signatures, JSON success/error shapes, error types (`CommandError`,
  `TimeoutExceeded`, `FileEditError`, `ValidationError`), ToolErrorPlugin format for
  unknown tools/bad arguments (`error` key).
- Limits: 5,000 chars for command output, edit diff and graph outputs; `read_file` 150
  lines and 10,000 chars; command timeout `min(300, max(5, remaining))`.
- Budget gate: `submit_patch` and `get_status` free; `budget_warning` when
  `tool_calls >= 20` and `remaining <= 10`.
- Path resolution (`/workspace/` and `/` stripped, `..` rejected), LLM argument coercion.
- `edit_file` 3-tier matching (exact → flexible re-indent → regex over code delimiters).
- Patch extraction: `git add -N . && git diff --binary HEAD`, protected test/config files
  stripped; fallback diff when the agent never submits.
- Prompt sections 1–7 and the three continuation nudges, `max_nudges = 3`.
- Reasoning: `chat_template_kwargs.enable_thinking` + `thinking_token_budget` (vLLM),
  defaults `max_output_tokens = 16384`, thinking budget 4096.

## Aligned with the swegemma 0.2.11 wheel (2026-11-07, read only)
Serialization `ensure_ascii=False`; `BudgetExceeded` ("Tool call budget exhausted (N calls)") checked
before session time (`TimeoutExceeded`, "Session time budget exhausted (X minutes)"); budget warning only
on counted tools and never on budget errors; `CommandError` message = stderr (or stdout);
`TimeoutExceeded` "Command timed out after N seconds"; `FileReadError`, `FileWriteError`,
`GraphLookupError`, `SubgraphExtractionError`; `read_file` start > end → `ValueError`; sizes in
characters; prompt instructions 0–5 verbatim.

## Declared differences
| Area | Official | TwinGuard | Why |
|---|---|---|---|
| Tools | 9 | 8: no `search_similar_code` | No embeddings for new repos (P2) |
| Graph | precomputed competition graphs | `twinguard_graph.build_graph`, same schema, rebuilt when sources change | Repos are ours; freshness after edits |
| Neighbor order / ties | undocumented | sorted ids; ties resolve to first sorted id | Determinism |
| Context compaction | ADK EventsCompaction (LLM summary) at 14,336 tokens | deterministic elision of tool outputs older than the last 5 messages, same threshold | An LLM summary would be a framing-exposed extra model call |
| Thoughts in history | depends on `include_thoughts` | not carried in history; logged in full by the controller | Context; analysis of §7.2 from the log |
| Turn | ADK `run_async` turn | one model call; loop ends right after the batch that calls `submit_patch` | Simpler, identical across arms |
| Agent instruction | competitor `agent.yaml` | fixed one-line instruction (`loop.AGENT_INSTRUCTION`) | No agent design is studied |
| Sandbox | Docker, `network_mode=none`, 4 GiB, 2 vCPU | subprocess backend (as the official one), scrubbed env; network off by the platform (Kaggle L4x4); commands, file tools and graph source reads as an unprivileged uid per slot | No Docker on Kaggle |
| Model call limits | ADK defaults | each model call (and its retries) bounded by the remaining session time; 4xx other than auth/not-found ends the episode as `bad_request` | Keeps every run inside its time budget |

## Frozen before the pilot
`harness.contract.contract_hash()` hashes every `harness/*.py`; it is logged in every
run's `start` event and goes into the freeze package (WP9). Budget values are calibrated
in the pilot with framing-blind criteria and then frozen.

Contract tests: `tests/test_harness_contract.py` (framing invariance of a 27-call script,
errors, truncation, budget gate, secrets scrubbed, patch stripping, edit tiers, loop
termination and nudges with a fake model).
