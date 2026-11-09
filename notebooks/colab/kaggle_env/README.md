# Kaggle environment for the Colab port

- `kaggle_freeze.txt`: `pip freeze --all` of the pinned Kaggle image
  (`gcr.io/kaggle-private-byod/python@sha256:37c64f7d…`, the one every TwinGuard kernel uses) right
  after the kernels' wheelhouse install (`--no-deps --force-reinstall`). Produced by the CPU probe
  kernel `manuelpz/twinguard-env-probe` (v4, 2026-11-09); no model, no competition data.
- `requirements.in`: the 41 wheelhouse packages, plus torch/torchvision/torchaudio, the evaluator
  and analysis packages, and the optional packages transformers/vLLM import when present
  (audio, video, vision, ray) that the Kaggle image has.
- `lock_base.txt`: their dependency closure with every version forced to Kaggle's
  (`uv pip compile requirements.in --override <kaggle freeze as name==version, wheelhouse included>
  --python-version 3.12 --python-platform x86_64-manylinux_2_31 --find-links <wheelhouse>
  --extra-index-url https://download.pytorch.org/whl/cu128 --index-strategy unsafe-best-match
  --no-emit-package <packages Kaggle lacks> --generate-hashes`), minus the wheelhouse packages.
  Packages Kaggle lacks are not installed either (`nvidia-cutlass-dsl` and its libs, which the
  kernels skip; `torch-c-dlpack-ext`, `google-cloud-bigquery-storage`, `httpx2`, `httpcore2`,
  `truststore`, `opentelemetry-exporter-otlp-proto-grpc`, `supervisor`, `nvidia-cuda-nvdisasm`).
- `colab_install()` installs `lock_base.txt` (`--no-deps --require-hashes`), then the wheelhouse files
  exactly as Kaggle does, checks every wheel against the hash Kaggle recorded, and fails unless the
  resulting freeze is a subset of `kaggle_freeze.txt`.
