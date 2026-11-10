# Kaggle environment for the Colab port

- `kaggle_freeze.txt`: `pip freeze --all` of the pinned Kaggle image
  (`gcr.io/kaggle-private-byod/python@sha256:37c64f7d…`, the one every TwinGuard kernel uses) right
  after the kernels' wheelhouse install (`--no-deps --force-reinstall`). Produced by the CPU probe
  kernel `manuelpz/twinguard-env-probe` (v4, 2026-11-09); no model, no competition data.
- `requirements.in`: the 41 wheelhouse packages, plus torch/torchvision/torchaudio, the evaluator
  and analysis packages, the optional packages transformers/vLLM import when present
  (audio, video, vision, ray) that the Kaggle image has, and the runtime-optional packages of the
  serving stack that no package declares but that change its code path when present (vLLM's
  server imports `uvloop`; uvicorn uses `uvloop`/`httptools`; FastAPI/pydantic `orjson`, `ujson`,
  `email-validator`; vLLM `xxhash`, `nvtx`; torch `optree`, `opt_einsum`; httpx/aiohttp/requests
  `brotli`, `zstandard`, `h2`, `chardet`, `simplejson`; `ml_dtypes`, `wcwidth`, `itsdangerous`).
  They were found by an AST scan of every installed wheel's imports against the Kaggle freeze
  (smoke 3 stopped at `import uvloop`); all at Kaggle's versions.
- `lock_base.txt`: their dependency closure with every version forced to Kaggle's
  (`uv pip compile requirements.in --override <kaggle freeze as name==version, wheelhouse included>
  --python-version 3.12 --python-platform x86_64-manylinux_2_31 --find-links <wheelhouse>
  --extra-index-url https://download.pytorch.org/whl/cu128 --index-strategy unsafe-best-match
  --no-emit-package <packages Kaggle lacks> --generate-hashes --no-header --no-annotate`), minus the
  wheelhouse packages (the override file also pins the wheelhouse packages, from their file names).
  Packages Kaggle lacks are not installed either (`nvidia-cutlass-dsl` and its libs, which the
  kernels skip; `torch-c-dlpack-ext`, `google-cloud-bigquery-storage`, `httpx2`, `httpcore2`,
  `truststore`, `opentelemetry-exporter-otlp-proto-grpc`, `supervisor`, `nvidia-cuda-nvdisasm`).
- `colab_install()` installs `lock_base.txt` (`--no-deps --require-hashes`), then the wheelhouse files
  exactly as Kaggle does, checks every wheel against the hash Kaggle recorded, and fails unless the
  resulting freeze is a subset of `kaggle_freeze.txt`.
- After the install, `colab_install()` imports the serving modules (`COLAB_IMPORT_PROBE`) and fails
  with the full list of missing imports before any model or server work.
