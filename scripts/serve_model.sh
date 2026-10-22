#!/usr/bin/env bash
# Mode 3: model-only server, no public business API and no LoRA at runtime.
set -euo pipefail
: "${ORDO_MODEL_PATH:?Set ORDO_MODEL_PATH to the final merged model directory}"
[[ -f "$ORDO_MODEL_PATH/config.json" ]] || { echo 'Missing model config.json' >&2; exit 1; }
export CUDA_VISIBLE_DEVICES="${GPU:-0}"
export PYTHONUNBUFFERED=1
exec "${ORDO_MODEL_PYTHON:-python}" -u -m vllm.entrypoints.cli.main serve "$ORDO_MODEL_PATH" \
  --host 127.0.0.1 --port "${MODEL_PORT:-8010}" --served-model-name ordo-final-2b \
  --dtype bfloat16 --max-model-len 8192 --gpu-memory-utilization "${GPU_MEMORY_UTILIZATION:-0.45}" \
  --max-num-seqs 16 --enable-prefix-caching --generation-config vllm
