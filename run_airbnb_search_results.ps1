$ErrorActionPreference = 'Stop'

# One-command launcher for Airbnb search extraction (PowerShell).
# Uses defaults from scripts/airbnb_search_urls.txt and DB/JSON output paths.

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$pythonBin = 'python'
if (Test-Path '.venv\Scripts\python.exe') {
  $pythonBin = '.venv\Scripts\python.exe'
}

& $pythonBin scripts/extract_airbnb_search_results.py `
  --urls-file scripts/airbnb_search_urls.txt `
  --max-scrolls 30 `
  --stop-after-stable-scrolls 4 `
  --delay-seconds 2.0 `
  --db-path data/airbnb_search_results.db `
  --output data/airbnb_search_results_batch.json
