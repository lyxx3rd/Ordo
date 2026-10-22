#!/usr/bin/env bash
set -euo pipefail
ORDO_SERVICE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="$ORDO_SERVICE_DIR${PYTHONPATH:+:$PYTHONPATH}"
exec "${ORDO_API_PYTHON:-python}" -u -m ordo_local.manage start \
  --config "${1:-$ORDO_SERVICE_DIR/config.local.json}"
