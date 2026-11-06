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
  the harness can pass it back as `reasoning_content` (`sampling['carry_reasoning']`, default off) and it then counts
  against the 32,768 context budget. **Decide in the smoke test**, together with whether vLLM accepts it on input.
- **Official harness answer (HARNESS_README §2.4, read 2026-11-06):** reasoning is enabled with
  `chat_template_kwargs.enable_thinking=true` plus `thinking_token_budget` (vLLM `ThinkingTokenBudgetLogitsProcessor`);
  official defaults `max_output_tokens=16384`, `thinking_budget=4096`, `max_model_len=32768`. The harness sends both
  (see `docs/harness.md`).
- **Native tool calling:** tools are declared in the system turn; calls are emitted as `<|tool_call>call:NAME{...}<tool_call|>`.
  To confirm in the smoke test: the vLLM `--tool-call-parser` for Gemma 4 and its malformed-call rate.

## Accounts and quotas

| Resource | Account | Notes |
|---|---|---|
| Kaggle | `manuelpz` (manuelpz.dev@gmail.com), CLI 2.2.5, access-token auth | Weekly quota 2026-11-06: GPU 45 h, TPU 20 h; refresh `2026-11-07T00:00Z` (Fri 6, 21:00 Chile). L4x4 quota multiplier unknown |
| Colab Pro | manu.medialab@gmail.com (linked to the Kaggle account above) | 400 compute units (as of 2026-11-05) |
| GitHub | `manuelpenazuniga` | Private repo |

## Kaggle probes (2026-11-06, kernel `manuelpz/twinguard-env-probe`, competition source `gemma-4-developer-agent`)

| Version | Requested | Server assigned | Internet | Result |
|---|---|---|---|---|
| 1 | `machine_shape: NvidiaL4X4`, internet on | **`NvidiaTeslaT4` (2x T4 15 GB)**, silent fallback | on: HF and PyPI reachable | wrong string or shape unavailable via CLI |
| 2 | `NvidiaL4X4`, internet off | **`NvidiaTeslaT4`**, silent fallback | off (HF/PyPI unreachable) | not an internet-gating issue |
| 3 | **`machine_shape: NvidiaL4`** (string read from the UI-configured notebook), internet off | **4x NVIDIA L4, 23,034 MiB each** | off (forced: UI says "Internet cannot be enabled for this competition with the current accelerator") | **works** |

L4x4 image (v3): same Python/torch/CUDA/driver as T4; 188 GB RAM, 48 CPUs, `/` overlay with 967 GB free (use `/tmp` for weights),
`/kaggle/working` 20 GB; GPU interconnect **PHB only (PCIe via host bridge, no NVLink)**, so TP=4 pays PCIe all-reduce; compare TP=2x2 and TP=1x4.
**No internet on L4x4**: vLLM wheels, model weights and code must arrive as private Kaggle datasets (or Kaggle Models), versioned by commit.

Image facts (T4 image, may differ on L4x4): Python 3.13.16, torch 2.11.0+cu130, CUDA 13.0, driver 580.178.04, **vLLM not preinstalled**,
`/kaggle/working` only **20 GB** (model is about 20 GB: download elsewhere), 31 GB RAM, 4 CPUs, **`unshare -rn` fails** (no user-namespace
network isolation for `run_command`). Competition data mounts at `/kaggle/input/competitions/gemma-4-developer-agent`.

Consequences: every kernel must start with a guard cell that aborts if the GPU is not the requested one (the server falls back silently);
attaching a notebook to a competition is `competition_sources` in `kernel-metadata.json`; the exact L4x4 shape string must be read
from a notebook where the L4x4 accelerator was selected in the UI (`kaggle kernels pull <id> -m`).

## Offline serving on Kaggle L4x4 (found 2026-11-06)

- **Weights from Kaggle Models**, no upload: `google/gemma-4/Other/gemma-4-31b-it-qat-w4a16-ct/2`
  (mounted at `/kaggle/input/models/google/gemma-4/other/gemma-4-31b-it-qat-w4a16-ct/2`).
  Smoke v1 hashed it against HF `52f3f65`: `model.safetensors` (sha256 1b9b1d62…), `tokenizer.json`,
  `config.json`, `generation_config.json` **identical**; `chat_template.jinja` (git f62ca843) and
  `tokenizer_config.json` (git af7f2586) are those of the HF **release revision `ca9d525`**, before
  "Update to canonical Gemma 4 chat template (#6)" and "Add response_template (#8)".
  Proposed serving: overlay dir = Kaggle weights + the two `52f3f65` files
  (`notebooks/model_overlay/`), so the served model is byte-identical to the preregistered revision.
  **Pending: author decision (and Astra's second opinion).**
- **Packages from the official wheelhouse** dataset `metric/gemma-4-developer-agent-wheelhouse`:
  vllm 0.19.1, transformers 5.13.1, flashinfer 0.6.6, google-adk 1.36.1, swegemma 0.2.11,
  adk-eval-core 0.1.0, adk-submission 0.2.13. Wheels are cp312: the kernel must use the official
  notebook's pinned image `gcr.io/kaggle-private-byod/python@sha256:37c64f7d…` (the default image is
  Python 3.13 and pip fails; smoke v1).
- **Official vLLM config** (HARNESS_README §3.1, getting-started notebook): TP=4,
  `--gpu-memory-utilization 0.90 --max-model-len 32768 --enable-auto-tool-choice
  --tool-call-parser gemma4 --reasoning-parser gemma4`, dtype bfloat16.
- Code reaches the kernel bundled inside the script from a git commit (`notebooks/build_kernel.py`);
  private dataset creation through the CLI failed silently on 2026-11-06.
- Reasoning: `chat_template_kwargs.enable_thinking` + `thinking_token_budget` (HARNESS_README §2.4).

## GPU environment — smoke test v3 (2026-11-06, kernel `manuelpz/twinguard-smoke-l4` v3, code 16deba9)

| Item | Value |
|---|---|
| GPU | 4x NVIDIA L4 23,034 MiB, driver 580.178.04, PCIe (no NVLink) |
| Image | `gcr.io/kaggle-private-byod/python@sha256:37c64f7d…` (Python 3.12) |
| Packages | vllm 0.19.1, torch 2.10.0+cu128, transformers 5.13.1 (official wheelhouse) |
| Serving | official `adk_submission.VllmServer`: TP=4, gpu_mem 0.90, max_model_len 32768, parsers gemma4, `--reasoning-config` gemma4 channel tags, `--no-scheduler-reserve-full-isl`, env `VLLM_MEMORY_PROFILER_ESTIMATE_CUDAGRAPHS=1` |
| Model files served | Kaggle weights + 52f3f65 overlay; all 6 checked files match HF 52f3f65 |
| Load | 384 s total (weights 110 s); 20.6 GB used per GPU |
| KV cache | 46,352 tokens; max concurrency at 32,768 tokens/request 8.74x |
| Reasoning | `enable_thinking` true → `reasoning_content` returned; `thinking_token_budget` accepted; off → none |
| Tool parser | structured `tool_calls`, no raw tags in content |
| Same seed twice | identical output (one test, thinking off) |
| Throughput (6.4k-token prompt, 1,024 max out, thinking on) | conc 1: 35 tok/s · 4: 127 · 8: 190 · 16: 314 (aggregate completion tok/s) |
| Harness episode (toy fixture, thinking on) | submitted S+-equivalent patch in 7 turns, 6 tool calls, 36 s |
| `usage.completion_tokens_details.reasoning_tokens` | not exposed (0); reasoning text is logged by the controller instead |

Notes: v1 failed (default image Python 3.13 vs cp312 wheels); v2 failed (raw `vllm.entrypoints` launch:
CUDA OOM warming the sampler with 256 dummy sequences; the official VllmServer config fixes it). TP=2x2
did not start after TP=4 in the same kernel (engine init failure; likely memory not yet released).
Proposal: fix TP=4, the official competition serving; no further GPU on the 2x2 comparison.
The WP7 run in this kernel used the superseded pilot templates and is discarded.

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
