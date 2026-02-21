# Airbnb extraction commands/scripts used

These are the scripts/commands used to build `airbnb_competitive_pricing_report.md`.

## 0) Install dependencies

```bash
pip install -r scripts/requirements-airbnb-extraction.txt
python -m playwright install firefox
```

## 1) Ratings + capacity metadata extraction

```bash
python scripts/extract_airbnb_ratings_and_capacity.py \
  --urls \
  https://www.airbnb.com/rooms/1056059527213736624 \
  https://www.airbnb.com/rooms/1454425652187314473 \
  https://www.airbnb.com/rooms/1150415234569647535 \
  https://www.airbnb.com/rooms/1457216363982722030 \
  https://www.airbnb.com/rooms/1111889905948527297 \
  https://www.airbnb.com/rooms/1258919267478775612 \
  https://www.airbnb.com/rooms/52844704 \
  https://www.airbnb.com/rooms/1480141488908865040 \
  https://www.airbnb.com/rooms/1234656316787706918 \
  https://www.airbnb.com/rooms/29804690 \
  https://www.airbnb.com/rooms/1201543696904281468 \
  https://www.airbnb.com/rooms/1179898885136709218 \
  https://www.airbnb.com/rooms/806590293406870588 \
  https://www.airbnb.com/rooms/2622950 \
  https://www.airbnb.com/rooms/765926351860435299 \
  https://www.airbnb.com/rooms/934308150078675066 \
  https://www.airbnb.com/rooms/35843844 \
  https://www.airbnb.com/rooms/1237279386552638340 \
  https://www.airbnb.com/rooms/661121154118134381 \
  --delay-seconds 2.0 \
  --output data/airbnb_ratings_capacity.json
```

## 2) Forward calendar availability extraction

```bash
python scripts/extract_airbnb_forward_calendar.py \
  --start-date 2026-03-01 \
  --urls \
  https://www.airbnb.com/rooms/1056059527213736624 \
  https://www.airbnb.com/rooms/1454425652187314473 \
  https://www.airbnb.com/rooms/1150415234569647535 \
  https://www.airbnb.com/rooms/1457216363982722030 \
  https://www.airbnb.com/rooms/1111889905948527297 \
  https://www.airbnb.com/rooms/1258919267478775612 \
  https://www.airbnb.com/rooms/52844704 \
  https://www.airbnb.com/rooms/1480141488908865040 \
  https://www.airbnb.com/rooms/1234656316787706918 \
  https://www.airbnb.com/rooms/29804690 \
  https://www.airbnb.com/rooms/1201543696904281468 \
  https://www.airbnb.com/rooms/1179898885136709218 \
  https://www.airbnb.com/rooms/806590293406870588 \
  https://www.airbnb.com/rooms/2622950 \
  https://www.airbnb.com/rooms/765926351860435299 \
  https://www.airbnb.com/rooms/934308150078675066 \
  https://www.airbnb.com/rooms/35843844 \
  https://www.airbnb.com/rooms/1237279386552638340 \
  https://www.airbnb.com/rooms/661121154118134381 \
  --delay-seconds 2.0 \
  --output data/airbnb_forward_calendar.json
```

## Notes
- Browser engine: Playwright Firefox (headless).
- Ratings source: JSON-LD `aggregateRating.ratingValue`.
- Capacity source: visible listing summary line (`X guests · Y bedrooms · Z beds · W baths`).
- Calendar source: `data-testid="calendar-day-MM/DD/YYYY"` + `data-is-day-blocked`.
- Search results source: listing-card text + `/rooms/<id>` URLs from search cards.

- Rate limiting: both scripts support `--delay-seconds` and add small random jitter between listing requests to reduce burst traffic.


## 3) Search results page listing extraction

```bash
python scripts/extract_airbnb_search_results.py \
  --url "https://www.airbnb.com/s/Arlington--VA/homes?flexible_trip_lengths%5B%5D=one_week&monthly_start_date=2026-03-01&monthly_length=3&monthly_end_date=2026-06-01&refinement_paths%5B%5D=%2Fhomes&acp_id=48a17bc0-a789-4f7e-a125-53bcb9d3d0d1&date_picker_type=calendar&place_id=ChIJD6ene522t4kRk7D2Rchvz_g&search_type=user_map_move&query=Arlington%2C%20VA&search_mode=regular_search&price_filter_input_type=2&price_filter_num_nights=5&channel=EXPLORE&ne_lat=38.85439311052802&ne_lng=-77.08069749268549&sw_lat=38.84343854000935&sw_lng=-77.09580429105523&zoom=16.00252364891367&zoom_level=16.00252364891367&search_by_map=true" \
  --max-scrolls 30 \
  --stop-after-stable-scrolls 4 \
  --delay-seconds 2.0 \
  --db-path data/airbnb_search_results.db \
  --output data/airbnb_search_results.json
```


Batch mode (multiple search URLs from file):

```bash
python scripts/extract_airbnb_search_results.py \
  --urls-file scripts/airbnb_search_urls.txt \
  --max-scrolls 30 \
  --stop-after-stable-scrolls 4 \
  --delay-seconds 2.0 \
  --db-path data/airbnb_search_results.db \
  --output data/airbnb_search_results_batch.json
```


## 4) Dashboard UI

```bash
python src/airbnb_dashboard.py \
  --db-path data/airbnb_search_results.db \
  --port 8080
```


## Windows end-to-end setup

See `WINDOWS_AIRBNB_SETUP.md` for clone/pull, install, extraction, and UI launch steps on Windows.


## Linux/WSL end-to-end setup

See `LINUX_WSL_AIRBNB_SETUP.md` for clone/pull, dependency install, extraction, and UI launch on Linux/WSL.


## One-command launch scripts

- Linux/WSL/macOS: `./run_airbnb_search_results.sh`
- Windows PowerShell: `./run_airbnb_search_results.ps1`

Both scripts call `scripts/extract_airbnb_search_results.py` with the batch defaults and now run with **DEBUG logging by default**.
