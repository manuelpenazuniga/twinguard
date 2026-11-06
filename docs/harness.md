# TwinGuard harness (WP2) — contract and declared differences

`harness/` is **API-compatible** with the official competition harness (`swegemma` +
`adk-eval-core`), replicated from the competition's `HARNESS_README.md` (sections 4–8,
read 2026-11-06). Neither package is on PyPI and the competition files ship only the
README and Dockerfiles, so the official harness cannot run in our environment
(protocol §7.1: the replica is used and declared). The README itself is competition
material and is **not** copied into this repo.

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

## Declared differences
| Area | Official | TwinGuard | Why |
|---|---|---|---|
| Tools | 9 | 8: no `search_similar_code` | No embeddings for new repos (P2) |
| Graph | precomputed competition graphs | `twinguard_graph.build_graph`, same schema, rebuilt when sources change | Repos are ours; freshness after edits |
| Neighbor order / ties | undocumented | sorted ids; ties resolve to first sorted id | Determinism |
| Budget-exhausted response | undocumented | `error_type: BudgetExhausted`, call not executed | Needed a defined behaviour |
| Context compaction | ADK EventsCompaction (LLM summary) at 14,336 tokens | deterministic elision of tool outputs older than the last 5 messages, same threshold | An LLM summary would be a framing-exposed extra model call |
| Thoughts in history | depends on `include_thoughts` | not carried in history; logged in full by the controller | Context; analysis of §7.2 from the log |
| Turn | ADK `run_async` turn | one model call; loop ends right after the batch that calls `submit_patch` | Simpler, identical across arms |
| Agent instruction | competitor `agent.yaml` | fixed one-line instruction (`loop.AGENT_INSTRUCTION`) | No agent design is studied |
| Sandbox | Docker, `network_mode=none`, 4 GiB, 2 vCPU | subprocess backend (as the official one), scrubbed env; network off by the platform (Kaggle L4x4) | No Docker on Kaggle |

## Frozen before the pilot
`harness.contract.contract_hash()` hashes every `harness/*.py`; it is logged in every
run's `start` event and goes into the freeze package (WP9). Budget values are calibrated
in the pilot with framing-blind criteria and then frozen.

Contract tests: `tests/test_harness_contract.py` (framing invariance of a 27-call script,
errors, truncation, budget gate, secrets scrubbed, patch stripping, edit tiers, loop
termination and nudges with a fake model).
