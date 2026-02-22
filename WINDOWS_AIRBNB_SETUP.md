# Windows setup guide: Airbnb extractor + dashboard

This guide shows exactly how to clone from Git, install dependencies, run extraction, and open the UI in your browser on Windows.

## 1) Prerequisites

- **Git for Windows**: https://git-scm.com/download/win
- **Python 3.10+**: https://www.python.org/downloads/windows/
  - During install, check **"Add Python to PATH"**.

## 2) Clone the repo

Open **PowerShell** and run:

```powershell
git clone https://github.com/<YOUR_ORG_OR_USER>/ml-tutorial.git
cd ml-tutorial
```

If you already cloned before:

```powershell
cd ml-tutorial
git pull
```

## 3) Create and activate virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks script execution, run once:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Then activate again.

## 4) Install dependencies

```powershell
pip install -r requirements.txt
python -m playwright install firefox
```

## 5) Run extractor (batch over the 3 search URLs)

This uses `scripts/airbnb_search_urls.txt`, writes JSON, and updates SQLite DB.

```powershell
python scripts/extract_airbnb_search_results.py `
  --urls-file scripts/airbnb_search_urls.txt `
  --max-scrolls 30 `
  --stop-after-stable-scrolls 4 `
  --delay-seconds 2.0 `
  --db-path data/airbnb_search_results.db `
  --output data/airbnb_search_results_batch.json
```

After success, you should have:

- `data/airbnb_search_results_batch.json`
- `data/airbnb_search_results.db`

## 6) Launch UI dashboard

```powershell
python src/airbnb_dashboard.py --db-path data/airbnb_search_results.db --port 8080
```

Open your browser to:

- http://127.0.0.1:8080

You will see a styled table with:
- Active status
- Listing URL/ID
- Rating
- Review count
- Price per night
- Source URL
- Last seen timestamp

## 7) Typical rerun workflow

Each time you want fresh data:

1. Activate env: `\.venv\Scripts\Activate.ps1`
2. Run extractor command from step 5
3. Refresh browser tab on `http://127.0.0.1:8080`

## Troubleshooting

- **`python` not found**: reinstall Python and enable PATH checkbox.
- **Playwright browser launch errors**: rerun `python -m playwright install firefox`.
- **No rows in UI**: confirm extractor completed and DB path matches:
  - extractor `--db-path`
  - dashboard `--db-path`


## Shortcut: run with one command

- Windows PowerShell: `./run_airbnb_search_results.ps1`
- Linux/WSL: `./run_airbnb_search_results.sh`
