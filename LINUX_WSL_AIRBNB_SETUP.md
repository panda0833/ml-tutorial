# Linux/WSL setup guide: Airbnb extractor + dashboard

This guide is for running the Airbnb extraction + UI stack on **Linux** or **WSL (Ubuntu)**.

## 1) Install prerequisites

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip
```

## 2) Clone (or pull) the repo

```bash
git clone https://github.com/<YOUR_ORG_OR_USER>/ml-tutorial.git
cd ml-tutorial
```

If already cloned:

```bash
cd ml-tutorial
git pull
```

## 3) Create and activate venv

```bash
python3 -m venv .venv
source .venv/bin/activate
```

## 4) Install Python deps + Playwright browser

```bash
pip install -r scripts/requirements-airbnb-extraction.txt
python -m playwright install firefox
```

If Playwright reports missing OS packages, run:

```bash
python -m playwright install-deps firefox
```

## 5) Run extraction (batch mode from URL file)

This reads URLs from `scripts/airbnb_search_urls.txt`, writes JSON, and updates SQLite DB.

```bash
python scripts/extract_airbnb_search_results.py \
  --urls-file scripts/airbnb_search_urls.txt \
  --max-scrolls 30 \
  --stop-after-stable-scrolls 4 \
  --delay-seconds 2.0 \
  --db-path data/airbnb_search_results.db \
  --output data/airbnb_search_results_batch.json
```

Expected outputs:
- `data/airbnb_search_results_batch.json`
- `data/airbnb_search_results.db`

## 6) Run dashboard UI

```bash
python src/airbnb_dashboard.py --db-path data/airbnb_search_results.db --port 8080
```

Open in browser:
- `http://127.0.0.1:8080`

### Access from Windows browser when using WSL

Usually `http://localhost:8080` on Windows works directly for WSL2.
If not, get WSL IP and use it:

```bash
hostname -I
```

Then open `http://<wsl-ip>:8080` from Windows browser.

## 7) Typical rerun cycle

1. `cd ml-tutorial`
2. `source .venv/bin/activate`
3. Run extraction command (step 5)
4. Refresh UI page

## Troubleshooting

- **`python: command not found`**: use `python3` and ensure Python is installed.
- **Playwright launch errors**: run `python -m playwright install firefox` and `python -m playwright install-deps firefox`.
- **Empty dashboard**: confirm extractor succeeded and `--db-path` matches dashboard `--db-path`.
- **Port in use**: launch dashboard with another port, e.g. `--port 8090`.


## Shortcut: run with one command

- Windows PowerShell: `./run_airbnb_search_results.ps1`
- Linux/WSL: `./run_airbnb_search_results.sh`
