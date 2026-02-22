#!/usr/bin/env python3
"""Extract Airbnb listing cards from one or more search results pages.

Also persists normalized listing records into SQLite for UI/reporting use.
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import re
import sqlite3
import time
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse, parse_qs

from playwright.sync_api import sync_playwright

ROOM_ID_RE = re.compile(r"/rooms/(\d+)")
RATING_PAREN_RE = re.compile(r"(\d(?:\.\d+)?)\s*\((\d[\d,]*)\)")
RATING_VERBOSE_RE = re.compile(r"(\d(?:\.\d+)?) out of 5 average rating,\s*(\d[\d,]*) reviews", re.I)
DATE_RANGE_RE = re.compile(r"\b([A-Z][a-z]{2}\s+\d{1,2}\s*[–-]\s*\d{1,2})\b")
PRICE_FOR_NIGHTS_RE = re.compile(r"\$([\d,]+)\s*for\s*(\d+)\s*nights?", re.I)
PRICE_LINE_RE = re.compile(r"\$([\d,]+)")
NIGHTS_LINE_RE = re.compile(r"for\s*(\d+)\s*nights?", re.I)

logger = logging.getLogger("airbnb_search_extractor")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS listings (
    listing_url TEXT PRIMARY KEY,
    listing_id TEXT NOT NULL,
    source_url TEXT NOT NULL,
    source_label TEXT,
    rating REAL,
    review_count INTEGER,
    date_range_text TEXT,
    total_price INTEGER,
    nights INTEGER,
    price_per_night REAL,
    active INTEGER NOT NULL DEFAULT 1,
    last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--url", help="Single Airbnb search results URL")
    p.add_argument("--urls-file", help="Path to text file containing one search URL per line")
    p.add_argument("--output", required=True, help="Output JSON path")
    p.add_argument("--db-path", default="data/airbnb_search_results.db", help="SQLite DB path")
    p.add_argument("--max-scrolls", type=int, default=30, help="Maximum number of scroll iterations")
    p.add_argument("--stop-after-stable-scrolls", type=int, default=4, help="Stop after this many scrolls with no new listing URLs")
    p.add_argument("--scroll-delay-seconds", type=float, default=1.5)
    p.add_argument("--delay-seconds", type=float, default=2.0, help="Optional pre-extract delay")
    p.add_argument("--timeout-ms", type=int, default=90_000)
    p.add_argument("--log-level", default="DEBUG", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = p.parse_args()
    if not args.url and not args.urls_file:
        p.error("Provide either --url or --urls-file")
    return args


def source_label_from_url(url: str) -> str:
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    query = qs.get("query", [None])[0]
    if query:
        return unquote(query)
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) >= 2 and parts[0] == "s":
        return unquote(parts[1]).replace("--", " ")
    return parsed.netloc


def short_source(url: str) -> str:
    label = source_label_from_url(url)
    return f"{label[:42]}..." if len(label) > 45 else label


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
    return list(dict.fromkeys(urls))


def _extract_from_search_page(page, url: str, args: argparse.Namespace) -> dict[str, Any]:
    source_label = source_label_from_url(url)
    logger.info("Processing source: %s", short_source(url))

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
            logger.info("[%s] listing_id=%s", short_source(url), listing_id)

    return {
        "source_url": url,
        "source_label": source_label,
        "count": len(by_listing),
        "results": sorted(by_listing.values(), key=lambda x: int(x["listing_id"])),
    }


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(SCHEMA_SQL)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(listings)").fetchall()}
    if "source_label" not in cols:
        conn.execute("ALTER TABLE listings ADD COLUMN source_label TEXT")


def persist_results_to_db(payload: dict[str, Any], db_path: str) -> None:
    db_file = Path(db_path)
    db_file.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db_file) as conn:
        _ensure_schema(conn)

        for source in payload.get("sources", []):
            source_url = source.get("source_url")
            source_label = source.get("source_label") or source_label_from_url(source_url or "")
            if not source_url:
                continue

            conn.execute("UPDATE listings SET active = 0 WHERE source_url = ?", (source_url,))
            for row in source.get("results", []):
                conn.execute(
                    """
                    INSERT INTO listings (
                        listing_url, listing_id, source_url, source_label, rating, review_count,
                        date_range_text, total_price, nights, price_per_night, active, last_seen_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, CURRENT_TIMESTAMP)
                    ON CONFLICT(listing_url) DO UPDATE SET
                        listing_id=excluded.listing_id,
                        source_url=excluded.source_url,
                        source_label=excluded.source_label,
                        rating=excluded.rating,
                        review_count=excluded.review_count,
                        date_range_text=excluded.date_range_text,
                        total_price=excluded.total_price,
                        nights=excluded.nights,
                        price_per_night=excluded.price_per_night,
                        active=1,
                        last_seen_at=CURRENT_TIMESTAMP
                    """,
                    (
                        row.get("listing_url"),
                        row.get("listing_id"),
                        source_url,
                        source_label,
                        row.get("rating"),
                        row.get("review_count"),
                        row.get("date_range_text"),
                        row.get("total_price"),
                        row.get("nights"),
                        row.get("price_per_night"),
                    ),
                )

        conn.commit()


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level), format="%(levelname)s %(message)s")
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
                per_source.append({
                    "source_url": url,
                    "source_label": source_label_from_url(url),
                    "error": str(exc),
                    "count": 0,
                    "results": [],
                })
                logger.error("Failed source %s: %s", short_source(url), exc)
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
    persist_results_to_db(payload, args.db_path)
    logger.info(
        "Wrote %s (%s sources, %s listings); updated database %s",
        out_path,
        payload["total_sources"],
        payload["total_listings"],
        args.db_path,
    )


if __name__ == "__main__":
    main()
