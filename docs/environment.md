# Environment record (WP1)

Status: **pre-smoke facts only.** The GPU section is filled in from `notebooks/smoke_a100.ipynb`.

## Model (verified 2026-11-06 via the Hugging Face API, no token)

| Field | Value |
|---|---|
| Canonical id | `google/gemma-4-31B-it-qat-w4a16-ct` (capital `B`; `...-31b-...` is a 307 redirect to it) |
| Revision to pin | `52f3f65bc7a02d555763bc923bd1d9094898219d` (lastModified 2026-07-20) |
| Gated | **No.** License `apache-2.0`. `HF_TOKEN` is not required to download; it is optional (rate limits only) |
| Files | `model.safetensors` (single file), `chat_template.jinja`, `config.json`, `generation_config.json`, `tokenizer*.json`, `processor_config.json` |
| `generation_config.json` | `temperature 1.0`, `top_p 0.95`, `top_k 64`, `do_sample true`, `eos_token_id [1, 106, 50]`; matches protocol §7.3 |

`model_id` in every data row must be exactly the canonical id above (the analysis rejects more than one value).

## Chat template (revision above, `chat_template.jinja`, "Gemma 4 Canonical Chat Template", published 2026-07-09)

- **Reasoning mode** is a template variable: `enable_thinking` (default `false`). In vLLM it should be passed per request as
  `extra_body={"chat_template_kwargs": {"enable_thinking": true}}`. **To confirm on vLLM in the smoke test**, together with
  whether vLLM returns the thought channel separately (`reasoning_content`) and which `--reasoning-parser` that requires.
- Thoughts are rendered as `<|channel>thought ... <channel|>`. Prior thoughts are re-rendered only for assistant turns after the
  last user message (`thinking_gate`), or for tool-calling turns when `preserve_thinking=true`. In an agent loop all
  assistant turns come after the last user message, so reasoning stays in context within the episode by default;
  the harness must pass it back as `reasoning_content` and count it against the 32,768 context budget.
- **Native tool calling:** tools are declared in the system turn; calls are emitted as `<|tool_call>call:NAME{...}<tool_call|>`.
  To confirm in the smoke test: the vLLM `--tool-call-parser` for Gemma 4 and its malformed-call rate.

## Accounts and quotas

| Resource | Account | Notes |
|---|---|---|
| Kaggle | `manuelpz` (manuelpz.dev@gmail.com), CLI 2.2.5, access-token auth | Weekly quota 2026-11-06: GPU 45 h, TPU 20 h; refresh `2026-11-07T00:00Z` (21:00 Chile, Fri 6) |
| Colab Pro | manu.medialab@gmail.com (linked to the Kaggle account above) | 400 compute units (as of 2026-11-05) |
| GitHub | `manuelpenazuniga` | Private repo |

## GPU environment (to fill from the smoke test)

| Field | Value |
|---|---|
| Platform / GPU / driver / CUDA | |
| vLLM version | |
| Load time (cold, warm) | |
| Peak GPU memory | |
| Throughput (tok/s at concurrency 1/4/8/16) | |
| Units or quota hours per hour | |
| Reasoning flag that works | |
| Tool-call parser and malformed-call rate | |
| Network isolation for `run_command` (`unshare -n`?) | |
| `environment_id` formula | |
