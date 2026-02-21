#!/usr/bin/env python3
"""Extract forward-looking Airbnb calendar availability statistics.

This script automates:
1) open listing page
2) click 'Check availability'
3) click calendar next button once (to move beyond current month)
4) parse calendar-day-* nodes
5) keep only dates >= --start-date
6) compute booked/available counts + percentages + compressed date ranges

Usage:
python scripts/extract_airbnb_forward_calendar.py \
  --start-date 2026-03-01 \
  --urls https://www.airbnb.com/rooms/1056059527213736624 ... \
  --output data/airbnb_forward_calendar.json
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import random
import re
import time
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright

DAY_RE = re.compile(r"calendar-day-(\d{2}/\d{2}/\d{4})")
ROOM_ID_RE = re.compile(r"/rooms/(\d+)")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--urls", nargs="+", required=True)
    p.add_argument("--start-date", required=True, help="ISO date, e.g. 2026-03-01")
    p.add_argument("--output", required=True)
    p.add_argument("--timeout-ms", type=int, default=45_000)
    p.add_argument("--delay-seconds", type=float, default=2.0, help="Delay between listing requests")
    return p.parse_args()


def room_id(url: str) -> str:
    m = ROOM_ID_RE.search(url)
    return m.group(1) if m else "unknown"


def compress_ranges(dates: list[str]) -> list[str]:
    if not dates:
        return []
    dts = [dt.date.fromisoformat(d) for d in sorted(dates)]
    out: list[tuple[dt.date, dt.date]] = []
    start = prev = dts[0]
    for cur in dts[1:]:
        if cur - prev == dt.timedelta(days=1):
            prev = cur
            continue
        out.append((start, prev))
        start = prev = cur
    out.append((start, prev))

    return [
        f"{a.isoformat()} to {b.isoformat()}" if a != b else a.isoformat()
        for a, b in out
    ]


def extract_listing(page, url: str, start_date: dt.date, timeout_ms: int) -> dict[str, Any]:
    page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)

    # Open calendar modal
    opened = False
    for sel in ['button[data-testid="homes-pdp-cta-btn"]', "button:has-text('Check availability')"]:
        try:
            page.locator(sel).first.click(timeout=10_000)
            opened = True
            break
        except Exception:
            continue

    if not opened:
        return {"url": url, "listing_id": room_id(url), "error": "calendar button not found"}

    # Move to forward month view
    for sel in [
        'button[data-testid="calendar-next-button"]',
        'button[aria-label*="Next"]',
        'button[aria-label*="next"]',
    ]:
        try:
            page.locator(sel).first.click(timeout=2_000)
            break
        except Exception:
            continue

    page.wait_for_timeout(700)

    raw_days = page.eval_on_selector_all(
        '[data-testid^="calendar-day-"]',
        "els => els.map(el => [el.getAttribute('data-testid'), el.getAttribute('data-is-day-blocked')])",
    )

    by_date: dict[str, bool] = {}
    for testid, blocked in raw_days:
        m = DAY_RE.match(testid or "")
        if not m:
            continue
        date_iso = dt.datetime.strptime(m.group(1), "%m/%d/%Y").date().isoformat()
        if dt.date.fromisoformat(date_iso) < start_date:
            continue
        by_date[date_iso] = blocked == "true"

    dates = sorted(by_date)
    booked = [d for d in dates if by_date[d]]
    available = [d for d in dates if not by_date[d]]

    total = len(dates)
    booked_n = len(booked)
    available_n = len(available)

    return {
        "url": url,
        "listing_id": room_id(url),
        "forward_days": total,
        "days_booked": booked_n,
        "days_not_booked": available_n,
        "vacancy_pct": round((available_n / total * 100), 1) if total else None,
        "occupancy_pct": round((booked_n / total * 100), 1) if total else None,
        "booked_ranges": compress_ranges(booked),
        "available_ranges": compress_ranges(available),
    }


def _sleep_with_jitter(base: float) -> None:
    if base <= 0:
        return
    time.sleep(base + random.uniform(0, 0.75))


def main() -> None:
    args = parse_args()
    start_date = dt.date.fromisoformat(args.start_date)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    with sync_playwright() as p:
        browser = p.firefox.launch(headless=True)
        context = browser.new_context(locale="en-US")
        for url in args.urls:
            page = context.new_page()
            try:
                results.append(extract_listing(page, url, start_date, timeout_ms=args.timeout_ms))
            except Exception as exc:  # noqa: BLE001
                results.append({"url": url, "listing_id": room_id(url), "error": str(exc)})
            finally:
                page.close()
            _sleep_with_jitter(args.delay_seconds)
        browser.close()

    out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
