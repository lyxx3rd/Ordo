#!/usr/bin/env bash
# Conservative PDF-layout line-break cleaning pipeline.
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <source.txt> <output_dir>" >&2
  exit 2
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE="$1"
OUTPUT_DIR="$2"
PYTHON_BIN="${LINEBREAK_PYTHON:-/home/liyunhan/miniconda3/envs/lyh/bin/python}"
API_URL="${LINEBREAK_API_URL:-http://127.0.0.1:8010/v1/completions}"
MODEL="${LINEBREAK_MODEL:-qwen3.5-2b-local}"
CONTEXT_CHARS="${LINEBREAK_CONTEXT_CHARS:-30}"
LEFT_CONTEXT_CHARS="${LINEBREAK_LEFT_CONTEXT_CHARS:-20}"
RIGHT_CONTEXT_CHARS="${LINEBREAK_RIGHT_CONTEXT_CHARS:-10}"
JOIN_THRESHOLD="${LINEBREAK_JOIN_THRESHOLD:-0.1}"

[[ -f "$SOURCE" ]] || { echo "Missing source file: $SOURCE" >&2; exit 1; }
mkdir -p "$OUTPUT_DIR"

STEM="$(basename "${SOURCE%.*}")"
CANDIDATES="$OUTPUT_DIR/${STEM}.linebreak_candidates.json"
SCORED="$OUTPUT_DIR/${STEM}.linebreak_scored.json"
CLEANED="$OUTPUT_DIR/${STEM}.cleaned.txt"
REPORT="$OUTPUT_DIR/${STEM}.cleaning_report.json"

"$PYTHON_BIN" "$ROOT/ordo/cleaning/prescreen_linebreak_candidates.py" \
  "$SOURCE" "$CANDIDATES" --context-chars "$CONTEXT_CHARS"

"$PYTHON_BIN" "$ROOT/ordo/cleaning/score_linebreak_context_gain_vllm.py" \
  "$CANDIDATES" "$SCORED" \
  --left-chars "$LEFT_CONTEXT_CHARS" --right-chars "$RIGHT_CONTEXT_CHARS" \
  --api-url "$API_URL" --model "$MODEL"

"$PYTHON_BIN" "$ROOT/ordo/cleaning/apply_linebreak_cleaning.py" \
  "$SOURCE" "$SCORED" "$CLEANED" "$REPORT" \
  --join-threshold "$JOIN_THRESHOLD"

echo "Pipeline complete."
echo "Cleaned text: $CLEANED"
echo "Audit report: $REPORT"
