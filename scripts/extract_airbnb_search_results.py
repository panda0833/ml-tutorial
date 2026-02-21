#!/usr/bin/env python3
"""Extract Airbnb listing cards from one or more search results pages.

Extracts per listing card:
- listing_url (canonical rooms URL)
- rating
- review_count
- date_range_text (e.g., "Mar 1–6")
- total_price (e.g., 691)
- nights (e.g., 5)
- price_per_night
- card_text (raw snippet for audit/debug)

Usage (single URL):
python scripts/extract_airbnb_search_results.py \
  --url "https://www.airbnb.com/s/Arlington--VA/homes?..." \
  --output data/airbnb_search_results.json

Usage (multiple URLs from file):
python scripts/extract_airbnb_search_results.py \
  --urls-file scripts/airbnb_search_urls.txt \
  --output data/airbnb_search_results_multi.json
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
RATING_PAREN_RE = re.compile(r"(\d(?:\.\d+)?)\s*\((\d[\d,]*)\)")
RATING_VERBOSE_RE = re.compile(r"(\d(?:\.\d+)?) out of 5 average rating,\s*(\d[\d,]*) reviews", re.I)
DATE_RANGE_RE = re.compile(r"\b([A-Z][a-z]{2}\s+\d{1,2}\s*[–-]\s*\d{1,2})\b")
PRICE_FOR_NIGHTS_RE = re.compile(r"\$([\d,]+)\s*for\s*(\d+)\s*nights?", re.I)
PRICE_LINE_RE = re.compile(r"\$([\d,]+)")
NIGHTS_LINE_RE = re.compile(r"for\s*(\d+)\s*nights?", re.I)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--url", help="Single Airbnb search results URL")
    p.add_argument("--urls-file", help="Path to text file containing one search URL per line")
    p.add_argument("--output", required=True, help="Output JSON path")
    p.add_argument("--max-scrolls", type=int, default=30, help="Maximum number of scroll iterations")
    p.add_argument("--stop-after-stable-scrolls", type=int, default=4, help="Stop after this many scrolls with no new listing URLs")
    p.add_argument("--scroll-delay-seconds", type=float, default=1.5)
    p.add_argument("--delay-seconds", type=float, default=2.0, help="Optional pre-extract delay")
    p.add_argument("--timeout-ms", type=int, default=90_000)
    args = p.parse_args()
    if not args.url and not args.urls_file:
        p.error("Provide either --url or --urls-file")
    return args


def _sleep_with_jitter(base: float) -> None:
    if base <= 0:
        return
    time.sleep(base + random.uniform(0, 0.75))


def _to_int(num_text: str | None) -> int | None:
    if not num_text:
        return None
    return int(num_text.replace(",", ""))


def _parse_card_fields(card_text: str) -> dict[str, Any]:
    rating = None
    review_count = None

    m = RATING_PAREN_RE.search(card_text)
    if m:
        rating = float(m.group(1))
        review_count = _to_int(m.group(2))
    else:
        m2 = RATING_VERBOSE_RE.search(card_text)
        if m2:
            rating = float(m2.group(1))
            review_count = _to_int(m2.group(2))

    date_range = None
    dm = DATE_RANGE_RE.search(card_text)
    if dm:
        date_range = dm.group(1).replace(" - ", "-").replace(" – ", "–")

    total_price = None
    nights = None
    pm = PRICE_FOR_NIGHTS_RE.search(card_text)
    if pm:
        total_price = _to_int(pm.group(1))
        nights = int(pm.group(2))
    else:
        p_line = PRICE_LINE_RE.search(card_text)
        n_line = NIGHTS_LINE_RE.search(card_text)
        if p_line:
            total_price = _to_int(p_line.group(1))
        if n_line:
            nights = int(n_line.group(1))

    price_per_night = None
    if total_price is not None and nights:
        price_per_night = round(total_price / nights, 2)

    return {
        "rating": rating,
        "review_count": review_count,
        "date_range_text": date_range,
        "total_price": total_price,
        "nights": nights,
        "price_per_night": price_per_night,
    }


def _load_urls(args: argparse.Namespace) -> list[str]:
    urls: list[str] = []
    if args.url:
        urls.append(args.url)
    if args.urls_file:
        for line in Path(args.urls_file).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                urls.append(line)
    # preserve order, dedupe
    return list(dict.fromkeys(urls))


def _extract_from_search_page(page, url: str, args: argparse.Namespace) -> dict[str, Any]:
    page.goto(url, wait_until="domcontentloaded", timeout=args.timeout_ms)
    _sleep_with_jitter(args.delay_seconds)

    seen_listing_ids: set[str] = set()
    stable_scrolls = 0
    for _ in range(args.max_scrolls):
        page.mouse.wheel(0, 3000)
        _sleep_with_jitter(args.scroll_delay_seconds)

        hrefs = page.eval_on_selector_all(
            'a[href*="/rooms/"]',
            'els => els.map(el => el.href)',
        )
        current_ids = {
            m.group(1)
            for h in hrefs
            for m in [ROOM_ID_RE.search(h or "")]
            if m
        }
        if len(current_ids) == len(seen_listing_ids):
            stable_scrolls += 1
        else:
            stable_scrolls = 0
            seen_listing_ids = current_ids

        if stable_scrolls >= args.stop_after_stable_scrolls:
            break

    raw_cards = page.evaluate(
        """
        () => {
          const anchors = [...document.querySelectorAll('a[href*="/rooms/"]')];
          return anchors.map(a => {
            const card = a.closest('[itemprop="itemListElement"], [data-testid="card-container"], div[role="group"]') || a.parentElement;
            return {
              href: a.href,
              card_text: (card?.innerText || '').trim()
            };
          });
        }
        """
    )

    by_listing: dict[str, dict[str, Any]] = {}
    for row in raw_cards:
        href = row.get("href") or ""
        m = ROOM_ID_RE.search(href)
        if not m:
            continue
        listing_id = m.group(1)
        listing_url = f"https://www.airbnb.com/rooms/{listing_id}"

        parsed = _parse_card_fields(row.get("card_text", ""))
        existing = by_listing.get(listing_id)
        score = sum(
            v is not None
            for v in [
                parsed["rating"],
                parsed["review_count"],
                parsed["date_range_text"],
                parsed["total_price"],
                parsed["nights"],
            ]
        )
        existing_score = -1
        if existing:
            existing_score = sum(
                v is not None
                for v in [
                    existing.get("rating"),
                    existing.get("review_count"),
                    existing.get("date_range_text"),
                    existing.get("total_price"),
                    existing.get("nights"),
                ]
            )
        if not existing or score > existing_score:
            by_listing[listing_id] = {
                "listing_id": listing_id,
                "listing_url": listing_url,
                **parsed,
                "card_text": row.get("card_text", "")[:500],
            }

    return {
        "source_url": url,
        "count": len(by_listing),
        "results": sorted(by_listing.values(), key=lambda x: int(x["listing_id"])),
    }


def main() -> None:
    args = parse_args()
    urls = _load_urls(args)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    per_source: list[dict[str, Any]] = []
    with sync_playwright() as p:
        browser = p.firefox.launch(headless=True)
        context = browser.new_context(locale="en-US")
        for url in urls:
            page = context.new_page()
            try:
                per_source.append(_extract_from_search_page(page, url, args))
            except Exception as exc:  # noqa: BLE001
                per_source.append({"source_url": url, "error": str(exc), "count": 0, "results": []})
            finally:
                page.close()
            _sleep_with_jitter(args.delay_seconds)
        browser.close()

    payload = {
        "sources": per_source,
        "total_sources": len(per_source),
        "total_listings": sum(s.get("count", 0) for s in per_source),
    }
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {out_path} ({payload['total_sources']} sources, {payload['total_listings']} listings)")


if __name__ == "__main__":
    main()
