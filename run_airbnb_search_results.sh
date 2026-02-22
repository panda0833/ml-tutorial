#!/usr/bin/env bash
set -euo pipefail

# One-command launcher for Airbnb search extraction.
# Uses defaults from scripts/airbnb_search_urls.txt and DB/JSON output paths.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python}"

if [[ -x ".venv/bin/python" ]]; then
  PYTHON_BIN=".venv/bin/python"
fi

"$PYTHON_BIN" scripts/extract_airbnb_search_results.py \
  --urls-file scripts/airbnb_search_urls.txt \
  --max-scrolls 30 \
  --stop-after-stable-scrolls 4 \
  --delay-seconds 2.0 \
  --db-path data/airbnb_search_results.db \
  --output data/airbnb_search_results_batch.json
