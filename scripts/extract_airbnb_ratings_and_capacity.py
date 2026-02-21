#!/usr/bin/env python3
"""Extract Airbnb rating + capacity metadata for listing URLs.

Outputs:
- listing_id
- rating (from JSON-LD aggregateRating.ratingValue)
- review_count (from JSON-LD aggregateRating.reviewCount, if present)
- guests / bedrooms / beds / bathrooms (from visible summary text)

Usage:
python scripts/extract_airbnb_ratings_and_capacity.py \
  --urls https://www.airbnb.com/rooms/1056059527213736624 \
         https://www.airbnb.com/rooms/1454425652187314473 \
  --output data/airbnb_ratings_capacity.json
"""

from __future__ import annotations

import argparse
import json
import random
import re
import time
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright

ROOM_ID_RE = re.compile(r"/rooms/(\d+)")
CAPACITY_RE = re.compile(
    r"(\d+)\s+guests?\s*·\s*(\d+)\s+bedrooms?\s*·\s*(\d+)\s+beds?\s*·\s*([\d.]+)\s+baths?",
    re.IGNORECASE,
)
CAPACITY_RE_NO_BEDS = re.compile(
    r"(\d+)\s+guests?\s*·\s*(\d+)\s+bedrooms?\s*·\s*([\d.]+)\s+baths?",
    re.IGNORECASE,
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--urls", nargs="+", required=True, help="Airbnb listing URLs")
    p.add_argument("--output", required=True, help="Output JSON path")
    p.add_argument("--timeout-ms", type=int, default=30_000)
    p.add_argument("--delay-seconds", type=float, default=2.0, help="Delay between listing requests")
    return p.parse_args()


def room_id(url: str) -> str:
    m = ROOM_ID_RE.search(url)
    return m.group(1) if m else "unknown"


def extract_from_page(page, url: str, timeout_ms: int) -> dict[str, Any]:
    page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
    page.wait_for_timeout(1800)

    rating = None
    review_count = None
    for block in page.locator('script[type="application/ld+json"]').all_text_contents():
        try:
            parsed = json.loads(block)
        except json.JSONDecodeError:
            continue

        candidates = parsed if isinstance(parsed, list) else [parsed]
        for obj in candidates:
            if not isinstance(obj, dict):
                continue
            agg = obj.get("aggregateRating")
            if isinstance(agg, dict):
                rating = agg.get("ratingValue", rating)
                review_count = agg.get("reviewCount", review_count)

    text = page.evaluate('document.body ? document.body.innerText : ""')
    guests = bedrooms = beds = bathrooms = None
    m = CAPACITY_RE.search(text)
    if m:
        guests, bedrooms, beds, bathrooms = m.groups()
    else:
        m2 = CAPACITY_RE_NO_BEDS.search(text)
        if m2:
            guests, bedrooms, bathrooms = m2.groups()
            beds = "n/a"

    return {
        "url": url,
        "listing_id": room_id(url),
        "rating": rating,
        "review_count": review_count,
        "guests": guests,
        "bedrooms": bedrooms,
        "beds": beds,
        "bathrooms": bathrooms,
    }


def _sleep_with_jitter(base: float) -> None:
    if base <= 0:
        return
    time.sleep(base + random.uniform(0, 0.75))


def main() -> None:
    args = parse_args()
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    with sync_playwright() as p:
        browser = p.firefox.launch(headless=True)
        context = browser.new_context(locale="en-US")
        for url in args.urls:
            page = context.new_page()
            row = {"url": url, "listing_id": room_id(url)}
            try:
                row.update(extract_from_page(page, url, timeout_ms=args.timeout_ms))
            except Exception as exc:  # noqa: BLE001
                row["error"] = str(exc)
            finally:
                page.close()
            results.append(row)
            _sleep_with_jitter(args.delay_seconds)
        browser.close()

    out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
