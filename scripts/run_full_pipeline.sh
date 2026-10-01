#!/usr/bin/env bash
# Clean extracted text locally, then run online Qwen structure analysis and labeling.
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <source.txt> <output_dir>" >&2
  exit 2
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE="$1"
OUTPUT_DIR="$2"

"$ROOT/scripts/run_linebreak_cleaning_pipeline.sh" "$SOURCE" "$OUTPUT_DIR/cleaning"

STEM="$(basename "${SOURCE%.*}")"
CLEANED="$OUTPUT_DIR/cleaning/${STEM}.cleaned.txt"
"$ROOT/scripts/run_online_structure.sh" "$CLEANED" "$OUTPUT_DIR/structure"
