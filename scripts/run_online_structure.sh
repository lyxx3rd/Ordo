#!/usr/bin/env bash
# Run the online Qwen global-analysis and line-labeling stages on a UTF-8 text file.
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <cleaned.txt> <output_dir>" >&2
  exit 2
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE="$1"
OUTPUT_DIR="$2"
PYTHON_BIN="${ORDO_PYTHON:-/home/liyunhan/miniconda3/envs/lyh/bin/python}"
CONFIG="${ORDO_CONFIG:-$ROOT/ordo/config.yaml}"

[[ -f "$SOURCE" ]] || { echo "Missing source file: $SOURCE" >&2; exit 1; }
[[ -f "$CONFIG" ]] || { echo "Missing config file: $CONFIG" >&2; exit 1; }
mkdir -p "$OUTPUT_DIR"

STEM="$(basename "${SOURCE%.*}")"
GLOBAL="$OUTPUT_DIR/${STEM}_global_structure.json"

"$PYTHON_BIN" "$ROOT/ordo/qwen_global_structure.py" \
  "$SOURCE" --config "$CONFIG" --output "$GLOBAL"

"$PYTHON_BIN" "$ROOT/ordo/qwen_label_document.py" \
  "$SOURCE" --config "$CONFIG" --global-structure "$GLOBAL" --output-dir "$OUTPUT_DIR"
